# System
import subprocess
import os
import threading

# 3rd-party
from IPython import get_ipython 
from IPython.core.magic import line_magic, magics_class, Magics
from docopt import docopt, DocoptExit
import tempfile

@magics_class
class IPClusterMagics(Magics):
    """Launch an IPyParallel cluster.

Usage:
  %ipcluster [options]
  %ipcluster [options] -m <modules>...
  %ipcluster (-h | --help)
  %ipcluster --version
  
Options:
  -h --help                Show this screen.
  -v --version             Show version.
  -N --num_nodes <int>     Number of nodes (default 1).
  -n --num_engines <int>   Number of engines (default 1 per node).
  -m --modules <str>       Modules to load (default none).
  -e --env <str>           Conda env to load (default none).
  -t --time <time>         Time limit (default 30:00).
  -d --dir <path>          Directory to launch engines (default $HOME)
  -C --const <str>         SLURM contraint (default haswell).
  -q --queue <str>         SLURM queue (default interactive).
  -J --name <str>          Job name (default ipyparallel)
"""
    def __init__(self, shell):
        super().__init__(shell)
        self.define_strings()
    
    def define_strings(self):
        self.__version__ = "%ipcluster 0.1"
        
        # If we want to use sbatch
        self.header_template = """
#!/bin/bash -l
#SBATCH -J {name}
#SBATCH -q {queue}
#SBATCH -N {num_nodes}
#SBATCH -t {time}
#SBATCH -C {constraint}
#SBATCH -L SCRATCH
"""
        
        # If we want to use salloc
        self.salloc_template = 'salloc -J {name} -q {queue} -N {num_nodes} -t {time} -C {const} bash {script}'

        self.module_template = """
# Load modules
mod="{module}"
module load "$mod"
echo "Loaded module $mod"
export PATH=$PYTHONUSERBASE/bin:$PATH
"""
        self.env_template = """
# Load conda env
env="{env}"
source activate "$env"
echo "Loaded env $env"
"""
        self.engine_template = """
ipengine
echo "Started engine."
"""
        
        self.cluster_template = """
# Start controller
myip=$(ip addr show ipogif0 | grep '10\.' | awk '{{print $2}}' | awk -F'/' '{{print $1}}')
echo "My ip is '$myip'."
ipcontroller --ip="$myip" &
echo "Started controller"

# Start engines
srun -n {num_engines} bash {launch_script}
echo "Started engines."
"""

    def parse_args(self, line):
        # Valid syntax
        try:
            args = docopt(self.__doc__, argv=line.split(), version=self.__version__)
        # Invalid syntax
        except DocoptExit:
            print("Invalid syntax.")
            print(self.__doc__)
            return 
        # Other normal exit (--version)
        except SystemExit:
            args = {}
            
        defaults = {
            '--name': 'ipyparallel',
            '--num_nodes': 1,
            '--modules': None,
            '--env': None,
            '--queue': 'interactive',
            '--time': '30:00',
            '--const': 'haswell'
        }
        
        given = {key: val for key, val in args.items() if val}
        combined = {**defaults, **given}
        
        # Remove '--' from args
        parsed_args = {key[2:]: val for key, val in combined.items()}
        
        # Set number of engines
        if 'num_engines' not in parsed_args.keys():
            parsed_args['num_engines'] = parsed_args['num_nodes']
        
        return parsed_args
    
    def load_modules(self, fh, modules):
        if modules:
            for module in modules:
                mod_str = self.module_template.format(module=module) 
                fh.write(mod_str)
    
    def activate_env(self, fh, env):
        if env:
            env_str = self.env_template.format(env=env)
            fh.write(env_str)
        
    def start_engine(self, fh):
        fh.write(self.engine_template)
        
    def start_cluster(self, fh, num_engines, launch_script):
        cluster_str = self.cluster_template.format(
            num_engines=num_engines,
            launch_script=launch_script
        )
        fh.write(cluster_str)
    
    def create_launch_script(self, fh, modules, env):
        self.load_modules(fh, modules)
        self.activate_env(fh, env)
        self.start_engine(fh)
        
    def create_batch_script(self, fh, modules, env, num_engines, launch_script):
        self.load_modules(fh, modules)
        self.activate_env(fh, env)
        self.start_cluster(fh, num_engines, launch_script)
        
    def read_script(self, fh):
        fh.seek(0)
        print("Script:")
        print(subprocess.check_output(['cat', fh.name]).decode())
        print("EOF")
    
    def get_salloc_line(self, batch_script, args):
        return self.salloc_template.format(script=batch_script, **args)
    
    def system_thread(self, command, fhs):
        def execute(cmd, fhs):
            # Run command
            get_ipython().system(cmd)
            
            # Close temporary files
            for fh in fhs:
                fh.close()
                
        thread = threading.Thread(target=execute, args=(command, fhs))
        thread.start()
    
    def submit_job(self, args):
        batch_prefix = os.path.join(os.environ['SCRATCH'], '.ipcbatch')
        launch_prefix = os.path.join(os.environ['SCRATCH'], '.ipclaunch')
        
        # Create temporary files
        # They'll be destroyed after submission
        launch_fh = tempfile.NamedTemporaryFile('w', prefix=launch_prefix)
        batch_fh = tempfile.NamedTemporaryFile('w', prefix=batch_prefix)
        fhs = [launch_fh, batch_fh]
        
        # Create launch script
        launch_script = launch_fh.name
        self.create_launch_script(
            launch_fh,
            args['modules'],
            args['env']
        )

        # Create batch script
        batch_script = batch_fh.name
        self.create_batch_script(
            batch_fh,
            args['modules'], 
            args['env'],
            args['num_engines'],
            launch_script
        )

        # Run salloc
        salloc_line = self.get_salloc_line(batch_script, args)
        print(salloc_line)
        self.system_thread(salloc_line, fhs)

    @line_magic
    def ipcluster(self, line):
        # Parse arguments
        args = self.parse_args(line)
        
        # Exit on invalid syntax
        if not args:
            return

        self.submit_job(args)
    
ip = get_ipython()
ipcluster_magics = IPClusterMagics(ip)
ip.register_magics(ipcluster_magics)