# Copyright (c) Jupyter Development Team.
FROM jupyter/minimal-notebook:4.0

MAINTAINER Matthew Turner

USER jovyan

#Install Python 3 packages
RUN conda install --yes \
    'ipywidgets=4.0' \
    pandas \
    matplotlib \
    scipy \
    netcdf4 \
    xarray \
    && conda clean -yt

# Install Python 2 packages
# we'll install python2 as an conda environment
RUN conda create -p $CONDA_DIR/envs/python2 python=2.7 \
    'ipython=4.0*' \
    'ipywidgets=4.0*' \
    pandas \
    matplotlib \
    scipy \
    netcdf4 \
    xarray \
    && conda clean -yt

COPY . /home/jovyan/work


USER root

# install the vw python client for python3
RUN  pip install git+https://github.com/VirtualWatershed/vwmodels-python-client.git@capstone

RUN  pip install mpltools

# install the vw python client for python2
RUN $CONDA_DIR/envs/python2/bin/pip install git+https://github.com/VirtualWatershed/vwmodels-python-client.git@capstone

RUN $CONDA_DIR/envs/python2/bin/pip install mpltools
# Install Python 2 kernel spec globally to avoid permission problems when NB_UID
# switching at runtime.
RUN $CONDA_DIR/envs/python2/bin/python \
    $CONDA_DIR/envs/python2/bin/ipython \
    kernelspec install-self
