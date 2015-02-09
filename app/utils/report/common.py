# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Common functions for email reports creation."""

import pymongo
import types

import models
import models.report as mreport
import utils


DEFAULT_UNIQUE_KEYS = [
    models.ARCHITECTURE_KEY,
    models.BOARD_KEY,
    models.DEFCONFIG_FULL_KEY,
    models.MACH_KEY
]

JOB_SEARCH_FIELDS = [
    models.GIT_COMMIT_KEY,
    models.GIT_URL_KEY,
    models.GIT_BRANCH_KEY
]

DEFAULT_BASE_URL = u"http://kernelci.org"
DEFAULT_BOOT_URL = u"http://kernelci.org/boot/all/job"
DEFAULT_BUILD_URL = u"http://kernelci.org/build"


def save_report(job, kernel, r_type, status, errors, db_options):
    """Save the email report status in the database.

    It does not save the actual email report sent.

    :param job: The job name.
    :type job: str
    :param kernel: The kernel name.
    :type kernel: str
    :param r_type: The type of report to save.
    :type r_type: str
    :param status: The status of the send action.
    :type status: str
    :param errors: A list of errors from the send action.
    :type errors: list
    :param db_options: The mongodb database connection parameters.
    :type db_options: dict
    """
    utils.LOG.info("Saving '%s' report for '%s-%s'", r_type, job, kernel)

    name = "%s-%s" % (job, kernel)

    spec = {
        models.JOB_KEY: job,
        models.KERNEL_KEY: kernel,
        models.NAME_KEY: name,
        models.TYPE_KEY: r_type
    }

    database = utils.db.get_db_connection(db_options)

    prev_doc = utils.db.find_one2(
        database[models.REPORT_COLLECTION], spec_or_id=spec)

    if prev_doc:
        report = mreport.ReportDocument.from_json(prev_doc)
        report.status = status
        report.errors = errors

        utils.db.save(database, report)
    else:
        report = mreport.ReportDocument(name)
        report.job = job
        report.kernel = kernel
        report.r_type = r_type
        report.status = status
        report.errors = errors

        utils.db.save(database, report, manipulate=True)


def get_unique_data(results, unique_keys=None):
    """Get a dictionary with the unique values in the results.

    :param results: The `Cursor` to analyze.
    :type results: pymongo.cursor.Cursor
    :return A dictionary with the unique data found in the results.
    """
    unique_data = {}

    if not unique_keys:
        unique_keys = DEFAULT_UNIQUE_KEYS

    def _unique_value(results, keys):
        """Internal generator to return the unique values.

        :param results: The pymongo Cursor to iterate.
        :param keys: The list of keys.
        :type keys: list
        :return A tuple (key, value).
        """
        for key in keys:
            yield key, results.distinct(key)

    if isinstance(results, pymongo.cursor.Cursor):
        unique_data = {
            k: v for k, v in _unique_value(results, unique_keys)
        }
    return unique_data


def count_unique(to_count):
    """Count the number of values in a list.

    Traverse the list and consider only the valid values (non-None).

    :param to_count: The list to count.
    :type to_count: list
    :return The number of element in the list.
    """
    total = 0
    if isinstance(to_count, (types.ListType, types.TupleType)):
        filtered_list = None
        filtered_list = [x for x in to_count if x is not None]
        total = len(filtered_list)
    return total


def parse_job_results(results):
    """Parse the job results from the database creating a new data structure.

    This is done to provide a simpler data structure to create the email
    body.


    :param results: The job results to parse.
    :type results: `pymongo.cursor.Cursor` or a list of dict
    :return A tuple with the parsed data as dictionary.
    """
    parsed_data = None

    for result in results:
        if result:
            res_get = result.get

            git_commit = res_get(models.GIT_COMMIT_KEY, u"Unknown")
            git_url = res_get(models.GIT_URL_KEY, u"Unknown")
            git_branch = res_get(models.GIT_BRANCH_KEY, u"Unknown")

            parsed_data = {
                models.GIT_COMMIT_KEY: git_commit,
                models.GIT_URL_KEY: git_url,
                models.GIT_BRANCH_KEY: git_branch
            }

    return parsed_data


def get_git_data(job, kernel, db_options):
    """Retrieve the git data from a job.

    :param job: The job name.
    :type job: string
    :param kernel: The kernel name.
    :type kernel: string
    :param db_options: The mongodb database connection parameters.
    :type db_options: dict
    :return A tuple with git commit, url and branch.
    """
    spec = {
        models.JOB_KEY: job,
        models.KERNEL_KEY: kernel
    }

    database = utils.db.get_db_connection(db_options)

    git_results = utils.db.find(
        database[models.JOB_COLLECTION],
        0,
        0,
        spec=spec,
        fields=JOB_SEARCH_FIELDS)

    git_data = parse_job_results(git_results)
    if git_data:
        git_commit = git_data[models.GIT_COMMIT_KEY]
        git_url = git_data[models.GIT_URL_KEY]
        git_branch = git_data[models.GIT_BRANCH_KEY]
    else:
        git_commit = git_url = git_branch = u"Unknown"

    return (git_commit, git_url, git_branch)


def get_total_results(
        job, kernel, collection, db_options, lab_name=None, unique_keys=None):
    """Retrieve the total count and the unique data for a collection.

    :param job: The job name.
    :type job: string
    :param kernel: The kernel name.
    :type kernel: string
    :param collection: The collection name.
    :type collection: string.
    :param db_options: The mongodb database connection parameters.
    :type db_options: dict
    :param lab_name: The lab name.
    :type lab_name: string
    :param unique_keys: The unique keys to count.
    :type unique_keys: list
    :return A tuple with the total count and the unique elements.
    """
    spec = {
        models.JOB_KEY: job,
        models.KERNEL_KEY: kernel,
    }

    if lab_name:
        spec[models.LAB_NAME_KEY] = lab_name

    database = utils.db.get_db_connection(db_options)

    total_results, total_count = utils.db.find_and_count(
        database[collection],
        0,
        0,
        spec=spec)

    total_unique_data = get_unique_data(total_results.clone(), unique_keys)

    return (total_count, total_unique_data)