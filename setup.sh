# For the environment on cori, we need the tensorflow module
# with horovod plus my own installations of ipyparallel, jupyter, etc.
module load tensorflow/intel-horovod-mpi-1.6
export PYTHONPATH=/global/cscratch1/sd/sfarrell/tf-hvd-ipp/lib/python2.7/site-packages:$PYTHONPATH
export PATH=/global/cscratch1/sd/sfarrell/tf-hvd-ipp/bin:$PATH
