"""
XBlock for Staff Graded Points
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import io
import json
import logging

import markdown
import pkg_resources

from webob import Response
from web_fragments.fragment import Fragment
from xblock.core import XBlock
from xblock.fields import String, Float, Scope
from xblock.runtime import NoSuchServiceError
from xblock.scorable import ScorableXBlockMixin, Score
from xblockutils.resources import ResourceLoader
from xblockutils.studio_editable import StudioEditableXBlockMixin

try:
    from openedx.core.djangoapps.course_groups.cohorts import get_course_cohorts
except ImportError:
    get_course_cohorts = lambda course_key: []

try:
    from course_modes.models import CourseMode
    modes_for_course = CourseMode.modes_for_course
except ImportError:
    modes_for_course = lambda course_key: [('audit', 'Audit Track'), ('masters', "Master's Track"), ('verified', "Verified Track")]

from bulk_grades.api import get_score, set_score, ScoreCSVProcessor

_ = lambda text: text

log = logging.getLogger(__name__)


@XBlock.needs('settings')
@XBlock.needs('i18n')
@XBlock.needs('user')
class StaffGradedXBlock(StudioEditableXBlockMixin, ScorableXBlockMixin, XBlock):
    """
    Staff Graded Points block
    """
    display_name = String(
        display_name=_("Display Name"),
        help=_("The display name for this component."),
        scope=Scope.settings,
        default=_("Staff Graded Points"),
    )
    instructions = String(
        display_name=_("Instructions"),
        help=_("The instructions to the learner. Markdown format"),
        scope=Scope.content,
        multiline_editor=True,
        default=_("Your results will be graded offline"),
        runtime_options={'multiline_editor': 'html'},
    )
    weight = Float(
        display_name="Problem Weight",
        help=_(
            "Enter the number of points possible for this component.  "
            "The default value is 1.0.  "
        ),
        default=1.0,
        scope=Scope.settings,
        values={"min": 0},
    )
    has_score = True

    editable_fields = ('display_name', 'instructions', 'weight')

    def _get_current_username(self):
        return self.runtime.service(self, 'user').get_current_user().opt_attrs.get(
            'edx-platform.username')

    def resource_string(self, path):
        """Handy helper for getting resources from our kit."""
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    def student_view(self, context=None):
        """
        The primary view of the StaffGradedXBlock, shown to students
        when viewing courses.
        """
        frag = Fragment()
        frag.add_css(self.resource_string("static/css/staff_graded.css"))
        loader = ResourceLoader(__name__)
        _ = self.runtime.service(self, "i18n").ugettext

        # Add i18n js
        statici18n_js_url = self._get_statici18n_js_url()
        if statici18n_js_url:
            frag.add_javascript_url(self.runtime.local_resource_url(self, statici18n_js_url))

        frag.add_javascript(self.resource_string("static/js/src/staff_graded.js"))
        frag.initialize_js('StaffGradedXBlock')

        context['id'] = self.location.html_id()
        context['instructions'] = markdown.markdown(self.instructions)
        context['display_name'] = self.display_name
        context['is_staff'] = self.runtime.user_is_staff

        course_id = self.location.course_key
        context['available_cohorts'] = [cohort.name for cohort in get_course_cohorts(course_id=course_id)]
        context['available_tracks'] = [
            (mode.slug, mode.name) for mode in
            modes_for_course(course_id, only_selectable=False)
            ]

        if context['is_staff']:
            from crum import get_current_request
            from django.middleware.csrf import get_token
            context['import_url'] = self.runtime.handler_url(self, "csv_import_handler")
            context['export_url'] = self.runtime.handler_url(self, "csv_export_handler")
            context['poll_url'] = self.runtime.handler_url(self, "get_results_handler")
            context['csrf_token'] = get_token(get_current_request())
            frag.add_javascript(loader.load_unicode('static/js/src/staff_graded.js'))
            frag.initialize_js('StaffGradedProblem',
                               json_args={k: context[k]
                                          for k
                                          in ('csrf_token', 'import_url', 'export_url', 'poll_url', 'id')})

        try:
            score = get_score(self.location, self.runtime.user_id) or {}
            context['grades_available'] = True
        except NoSuchServiceError:
            context['grades_available'] = False
        else:
            if score:
                grade = score['score']
                context['score_string'] = _('{score} / {total} points').format(score=grade, total=self.weight)
            else:
                context['score_string'] = _('{total} points possible').format(total=self.weight)
        frag.add_content(loader.render_django_template('static/html/staff_graded.html', context))
        return frag

    # TO-DO: change this to create the scenarios you'd like to see in the
    # workbench while developing your XBlock.
    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("StaffGradedXBlock",
             """<staffgradedxblock/>
             """),
            ("Multiple StaffGradedXBlock",
             """<vertical_demo>
                <staffgradedxblock/>
                <staffgradedxblock/>
                <staffgradedxblock/>
                </vertical_demo>
             """),
        ]

    @staticmethod
    def _get_statici18n_js_url():
        """
        Returns the Javascript translation file for the currently selected language, if any.
        Defaults to English if available.
        """
        from django.utils import translation
        locale_code = translation.get_language()
        if locale_code is None:
            return None
        text_js = 'public/js/translations/{locale_code}/text.js'
        lang_code = locale_code.split('-')[0]
        for code in (locale_code, lang_code, 'en'):
            loader = ResourceLoader(__name__)
            if pkg_resources.resource_exists(
                    loader.module_name, text_js.format(locale_code=code)):
                return text_js.format(locale_code=code)
        return None

    @staticmethod
    def get_dummy():
        """
        Dummy method to generate initial i18n
        """
        from django.utils import translation
        return translation.gettext_noop('Dummy')

    @XBlock.handler
    def csv_import_handler(self, request, suffix=''):  # pylint: disable=unused-argument
        """
        Endpoint that handles CSV uploads.
        """
        if not self.runtime.user_is_staff:
            return Response('not allowed', status_code=403)

        _ = self.runtime.service(self, "i18n").ugettext

        try:
            score_file = request.POST['csv'].file
        except KeyError:
            data = {'error_rows': [1], 'error_messages': [_('missing file')]}
        else:
            log.info('Processing %d byte score file %s for %s', score_file.size, score_file.name, self.location)
            block_id = self.location
            block_weight = self.weight
            processor = ScoreCSVProcessor(
                block_id=str(block_id),
                max_points=block_weight,
                user_id=self.runtime.user_id)
            processor.process_file(score_file, autocommit=True)
            data = processor.status()
            log.info('Processed file %s for %s -> %s saved, %s processed, %s error. (async=%s)',
                     score_file.name,
                     block_id,
                     data.get('saved', 0),
                     data.get('total', 0),
                     len(data.get('error_rows', [])),
                     data.get('waiting', False))
        return Response(json.dumps(data), content_type='application/json')

    @XBlock.handler
    def csv_export_handler(self, request, suffix=''):  # pylint: disable=unused-argument
        """
        Endpoint that handles CSV downloads.
        """
        if not self.runtime.user_is_staff:
            return Response('not allowed', status_code=403)

        track = request.GET.get('track', None)
        cohort = request.GET.get('cohort', None)

        buf = io.StringIO()
        ScoreCSVProcessor(
            block_id=str(self.location),
            max_points=self.weight,
            display_name=self.display_name,
            track=track,
            cohort=cohort).write_file(buf)
        resp = Response(buf.getvalue())
        resp.content_type = 'text/csv'
        resp.content_disposition = 'attachment; filename="%s.csv"' % self.location
        return resp

    @XBlock.handler
    def get_results_handler(self, request, suffix=''):  # pylint: disable=unused-argument
        """
        Endpoint to poll for celery results.
        """
        if not self.runtime.user_is_staff:
            return Response('not allowed', status_code=403)
        try:
            result_id = request.POST['result_id']
        except KeyError:
            data = {'message': 'missing'}
        else:
            results = ScoreCSVProcessor().get_deferred_result(result_id)
            if results.ready():
                data = results.get()
                log.info('Got results from celery %r', data)
            else:
                data = {'waiting': True, 'result_id': result_id}
                log.info('Still waiting for %s', result_id)
        return Response(json.dumps(data), content_type='application/json')

    def max_score(self):
        return self.weight

    def get_score(self):
        """
        Return a raw score already persisted on the XBlock.  Should not
        perform new calculations.

        Returns:
            Score(raw_earned=float, raw_possible=float)
        """
        score = get_score(self.runtime.user_id, self.location)
        score = score or {'grade': 0, 'max_grade': 1}
        return Score(raw_earned=score['grade'], raw_possible=score['max_grade'])

    def set_score(self, score):
        """
        Persist a score to the XBlock.

        The score is a named tuple with a raw_earned attribute and a
        raw_possible attribute, reflecting the raw earned score and the maximum
        raw score the student could have earned respectively.

        Arguments:
            score: Score(raw_earned=float, raw_possible=float)

        Returns:
            None
        """
        state = json.dumps({'grader': self._get_current_username()})
        set_score(self.location,
                  self.runtime.user_id,
                  score.raw_earned,
                  score.raw_possible,
                  state=state)

    def publish_grade(self):
        pass
