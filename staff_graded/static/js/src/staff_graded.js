(function() {
  'use strict'

  function doneLoading(blockId, data) {
    $(`#${blockId}-spinner`).hide();
    if (data.error_rows.length || data.error_messages.length) {
      var message = '';
      if (data.error_rows.length) {
        message += interpolate_text(
          ngettext('{error_count} error. Please try again. ',
                   '{error_count} errors. Please try again. ',
                   data.error_rows.length),
          { error_count: data.error_rows.length });
      }
      if (data.error_messages.length) {
        message += '<br>';
        message += data.error_messages;
      }
    } else {
      var message = interpolate_text(
        ngettext('Processed {row_count} row. ',
                 'Processed {row_count} rows. ',
                 data.total), { row_count:data.total }) +
                    interpolate_text(
                      ngettext('Updated scores for {row_count} learner.',
                               'Updated scores for {row_count} learners.',
                               data.saved), { row_count: data.saved });
    }
    $(`#${blockId}-status`).show();
    $(`#${blockId}-status .message`).html(message);
  };

  function pollResults(blockId, poll_url, result_id) {
    $.ajax({
      url: poll_url,
      type: 'POST',
      data: {result_id: result_id},
      success: function(data) {
        if (data.waiting) {
          setTimeout(function(){
            pollResults(blockId, poll_url, result_id);
          }, 1000);
        } else {
          doneLoading(blockId, data);
        }
      }
    });
  };


  this.StaffGradedProblem = function(runtime, element, json_args) {
    var $element = $(element);
    var fileInput = $element.find('.file-input');
    var $exportButton = $element.find('.export-button');
    fileInput.change(function(e){
      var firstFile = this.files[0];
      var self = this;
      if (firstFile == undefined) {
        return;
      } else if (firstFile.size > 4194303) {
        var message = gettext('Files must be less than 4MB. Please split the file into smaller chunks and upload again.');
        $(`#${json_args.id}-status`).show();
        $(`#${json_args.id}-status .message`).html(message);
        return;
      }
      var formData = new FormData();
      formData.append('csrfmiddlewaretoken', json_args.csrf_token);
      formData.append('csv', firstFile);

      $element.find('.filename').html(firstFile.name);
      $element.find('.status').hide();
      $element.find('.spinner').show();
      $.ajax({
        url : json_args.import_url,
        type : 'POST',
        data : formData,
        processData: false,  // tell jQuery not to process the data
        contentType: false,  // tell jQuery not to set contentType
        success : function(data) {
          self.value = '';
          if (data.waiting) {
            setTimeout(function() {
              pollResults(json_args.id, json_args.poll_url, data.result_id);
            }, 1000);
          } else {
            doneLoading(json_args.id, data);
          }
        }
      });

    });

    $exportButton.click(function(e) {
        e.preventDefault();
        var url = $exportButton.attr('href') + '?' + $.param(
            {
                track: $element.find('.track-field').val(),
                cohort: $element.find('.cohort-field').val()
            }
        );
        location.href = url;
    });

  };

}).call(this);
