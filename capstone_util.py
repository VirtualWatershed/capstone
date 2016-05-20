"""
Run model on LC data, modify data.nc temperatures for a range of values,

"""
import netCDF4
import os
import shutil
import signal
import time
import urllib

from datetime import datetime
from IPython.display import clear_output

from client.model_client.client import ModelApiClient
from client.swagger_client.apis.default_api import DefaultApi


def run_many_prms(input_dirs, jwt,
                  auth_host='https://auth-test.virtualwatershed.org/api',
                  model_host='https://model-test.virtualwatershed.org/api',
                  clobber=True,
                  verify_ssl=False):
    """
    For every directory in the input_dirs, run PRMS using the modeling server.
    """

    cl = ModelApiClient(jwt, auth_host, model_host)
    api = DefaultApi(api_client=cl)

    mr_ids_title_lookup = {}
    for d in input_dirs:

        output_dir = d + '-output'
        if os.path.isdir(output_dir):
            shutil.rmtree(output_dir)

        os.makedirs(output_dir)

        mr = api.create_modelrun(
            modelrun=dict(title=output_dir, model_name='prms')
        )

        data_path = os.path.join(d, 'data.nc')
        param_path = os.path.join(d, 'parameter.nc')
        control_path = os.path.join(d, 'incline_village.control')

        print 'uploading data for input dir ' + d
        api.upload_resource_to_modelrun(mr.id, 'data', data_path)

        print 'uploading param for input dir ' + d
        api.upload_resource_to_modelrun(mr.id, 'param', param_path)

        print 'uploading control for input dir ' + d
        api.upload_resource_to_modelrun(mr.id, 'control', control_path)

        print 'starting model run for input dir {} mr.id {}'.format(d, mr.id)
        api.start_modelrun(mr.id)

        # save mr id for use in getting and displaying model run statuses
        mr_ids_title_lookup.update({mr.id: d})

    signal.signal(signal.SIGALRM, _timeout_handler)

    runs_finished = False
    state = {i: 'SUBMITTED' for i in mr_ids_title_lookup.keys()}
    while not runs_finished:

        for i, title in mr_ids_title_lookup.iteritems():

            print 'retrieving status for model run id {0} '\
                  'model run title {1}'.format(i, title)

            signal.alarm(2)

            state[i] = api.get_modelrun_by_id(i).progress_state

            signal.alarm(0)

            clear_output()
            print 'current state: {}'.format(state)

            runs_finished = (
                all([s == 'FINISHED' for s in state.values()]) or
                any([s == 'ERROR' for s in state.values()])
            )

            if not runs_finished:
                time.sleep(2.5)

    clear_output()
    print 'all runs finished, downloading results'
    # iterate over output_dir here since title and output dir are identical
    if not verify_ssl:
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context

    download_many_outputs(mr_ids_title_lookup.keys(), jwt)

    # for i, output_dir in mr_ids_title_lookup.iteritems():
        # mr = api.get_modelrun_by_id(i)
        # urllib.urlretrieve(
            # mr.resources[-1].resource_url,
            # os.path.join(output_dir, 'statsvar.nc')
        # )

    print 'all outputs have been downloaded'

    print 'list of modelruns run: {}'.format(mr_ids_title_lookup.keys())

    return None


def download_many_outputs(mr_ids, jwt, output_dirs=None):

    if output_dirs is None:
        use_mr_title_as_dir = True

    signal.signal(signal.SIGALRM, _timeout_handler)

    cl = ModelApiClient(jwt, 'https://auth-test.virtualwatershed.org/api',
                        'https://model-test.virtualwatershed.org/api')
    api = DefaultApi(api_client=cl)

    for idx, mr_id in enumerate(mr_ids):

        download_finished = False
        while not download_finished:

            try:

                signal.alarm(2)

                mr = api.get_modelrun_by_id(mr_id)

                if use_mr_title_as_dir:
                    output_dir = mr.title
                else:
                    output_dir = output_dirs[idx]

                urllib.urlretrieve(
                    mr.resources[-1].resource_url,
                    os.path.join(output_dir, 'statsvar.nc')
                )
                signal.alarm(0)

                download_finished = True

            except IOError as e:

                print e.message


def run_prms(data, param, control, jwt, output_dir, modelrun_title=None,
             auth_host='https://auth-test.virtualwatershed.org/api',
             model_host='https://model-test.virtualwatershed.org/api',
             clobber=True,
             verify_ssl=False):
    """
    Wrapper for running PRMS using the Virtual Watershed Modeling Service
    """
    if os.path.isdir(output_dir) and clobber:
        shutil.rmtree(output_dir)
    elif not clobber:
        raise RuntimeError('output_dir exists and clobber is False')

    os.makedirs(output_dir)

    # connect to server
    cl = ModelApiClient(jwt, auth_host, model_host)

    # model run
    if modelrun_title is None:
        modelrun_title = 'model-run-' + datetime.now().isoformat('T')

    api = DefaultApi(api_client=cl)
    mr = api.create_modelrun(
        modelrun=dict(title=modelrun_title, model_name='prms')
    )

    print "uploading data"
    api.upload_resource_to_modelrun(mr.id, 'data', data)

    print "uploading param"
    api.upload_resource_to_modelrun(mr.id, 'param', param)

    print "uploading control"
    api.upload_resource_to_modelrun(mr.id, 'control', control)

    print "starting modelrun"
    api.start_modelrun(mr.id)

    signal.signal(signal.SIGALRM, _timeout_handler)

    run_finished = False
    while not run_finished:

        try:
            clear_output()
            print 'getting state...'

            # set 5 second timeout for getting status
            signal.alarm(5)

            mr = api.get_modelrun_by_id(mr.id)
            state = mr.progress_state
            print 'state: ' + state

            if len(mr.progress_events) > 0:
                event = mr.progress_events[-1].event_name
                print 'event: ' + event

            run_finished = (state == 'ERROR' or state == 'FINISHED')

            signal.alarm(0)

            if not run_finished:
                time.sleep(2.0)

        except IOError as e:
            print e.message

    print 'run finished, downloading outputs to ' + output_dir

    # download outputs to output_dir
    # XXX Is statsvar always last?
    mr = api.get_modelrun_by_id(mr.id)

    if not verify_ssl:
        # this is the hack way according to a SO post I can no longer find
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context

    urllib.urlretrieve(
        mr.resources[-1].resource_url, os.path.join(output_dir, 'statsvar.nc')
    )


def _timeout_handler(signum, frame):
    raise IOError("Request to server timed out!")


def create_prms_scenario_inputs(orig_data,
                                orig_param,
                                orig_control,
                                scenario_directory,
                                data_mod_fun=None,
                                param_mod_fun=None,
                                clobber=True):
    """
    Provide vectorizable functions data_mod_fun and/or param_mod_fun to
    modify the original data and param files. Writes modified scenario files
    to scenario_directory for later use.

    Arguments:
        orig_data (str): path to data file
        orig_param (str): path to param file
        orig_control (str): path to control file
        scenario_directory (str): directory to write scenario data to;
            will be overwritten if exists
        data_mod_fun (function): function of the data netCDF, returns modified data netCDF
        param_mod_fun (function): function of the param netCDF, returns modified param netCDF
        clobber (bool): overwrite scenario directory if it exists

    Returns:
        None
    """
    if not os.path.isdir(scenario_directory):
        os.makedirs(scenario_directory)
    elif clobber:
        shutil.rmtree(scenario_directory)
        os.makedirs(scenario_directory)

    originals = [orig_data, orig_param, orig_control]
    scenario_paths = [
        os.path.join(scenario_directory, os.path.basename(orig))
        for orig in originals
    ]

    for o, p in zip(originals, scenario_paths):
        shutil.copy(o, p)

    # open copied scenario files for modification
    if data_mod_fun is not None:
        scenario_data = netCDF4.Dataset(scenario_paths[0], 'r+')
        data_mod_fun(scenario_data)
        scenario_data.close()

    if param_mod_fun is not None:
        scenario_param = netCDF4.Dataset(scenario_paths[1], 'r+')
        param_mod_fun(scenario_param)
        scenario_param.close()


def temperature_scaling_fun_generator(scale_factor,
                                      temp_vars=['tmax', 'tmin']):
    """
    Given a scale_factor and the temperature vars to modify, return a
    function that will modify all given temperature variables
    by that scale_factor.
    """
    def data_mod_fun(data_nc):

        for v in temp_vars:
            t = data_nc.variables[v]
            t[:] = scale_factor * t[:]

    return data_mod_fun


def scale_params_fun_generator(**param_factors):
    """
    Given a set of PRMS parameter-scalefactor pairs (e.g. jh_coeff_hru=0.9),
    generate a function that will scale each parameter by its accompanying
    scale factor.

    Example:
        Generate a function that will scale every hru's jh coefficient by
        1.1 and every rad_trncf coefficient by 0.9, in other words increasing
        the Jensen-Haise ET potential by 10% and decreasing the transmission
        coefficient for short-wave radiation through the winter vegetation
        canopy by 10% at every HRU.

        >>> fun = scale_params_fun_generator(jh_coeff_hru=1.1, rad_trncf=0.9)
    """
    def param_mod_fun(param_nc):

        params = param_nc.variables

        for v in param_factors.keys():
            if v not in params.keys():
                raise RuntimeError(
                    'parameter requested to modify is not present in param nc'
                )

            params[v][:] = param_factors[v]*params[v][:]

    return param_mod_fun


class Scenario:
    pass


if __name__ == '__main__':
    help_msg = '''

Usage:
    python compare_temperature_diffs.py 1.1 1.4 0.1

will run the model for four separate multiplicative factors of temperature
'''
