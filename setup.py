"""Setup for Staff Graded XBlock."""

import os
from setuptools import setup


def package_data(pkg, roots):
    """Generic function to find package_data.

    All of the files under each of the `roots` will be declared as package
    data for package `pkg`.

    """
    data = []
    for root in roots:
        for dirname, _, files in os.walk(os.path.join(pkg, root)):
            for fname in files:
                data.append(os.path.relpath(os.path.join(dirname, fname), pkg))

    return {pkg: data}


setup(
    name='staff_graded-xblock',
    version='0.4',
    description='Staff Graded XBlock',   # TODO: write a better description.
    license='AGPL v3',          # TODO: choose a license: 'AGPL v3' and 'Apache 2.0' are popular.
    packages=[
        'staff_graded',
    ],
    install_requires=[
        'markdown',
        'XBlock',
        'xblock-utils>=v1.0.0',
        'web-fragments',
        'edx-bulk-grades>=0.4',
    ],
    entry_points={
        'xblock.v1': [
            'staffgradedxblock = staff_graded:StaffGradedXBlock',
        ]
    },
    package_data=package_data("staff_graded", ["static", "public"]),
)
