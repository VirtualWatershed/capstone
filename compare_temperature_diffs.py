"""
Run model on LC data, modify data.nc temperatures for a range of values,

"""
import netCDF4
import os
import shutil
import signal
import sys
import time
import urllib

from datetime import datetime

from client.model_client.client import ModelApiClient
from client.swagger_client.apis.default_api import DefaultApi


def run_prms(data, param, control, jwt, output_dir, modelrun_title=None,
             auth_host='https://auth-test.virtualwatershed.org/api',
             model_host='https://model-test.virtualwatershed.org/api',
             clobber=True,
             verify_ssl=False):
    """
    Wrapper for running PRMS using the
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

    def timeout_handler(signum, frame):
        raise IOError("Request to server timed out!")
    signal.signal(signal.SIGALRM, timeout_handler)

    run_finished = False
    while not run_finished:

        try:
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
                time.sleep(7.5)

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
    def data_mod_fun(data_nc):

        for v in temp_vars:
            t = data_nc.variables[v]
            t[:] = scale_factor * t[:]

    return data_mod_fun


class Scenario:
    pass


if __name__ == '__main__':
    help_msg = '''

Usage:
    python compare_temperature_diffs.py 1.1 1.4 0.1

will run the model for four separate multiplicative factors of temperature
'''
