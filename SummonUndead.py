from __future__ import print_function

from IPython.core.magic import Magics, magics_class, line_magic, cell_magic, line_cell_magic
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring

import pickle
from tempfile import NamedTemporaryFile, TemporaryDirectory 
from jinja2 import Template

import types

import subprocess
import time

from joblib.externals.loky import set_loky_pickler
from joblib import parallel_backend
from joblib import Parallel, delayed
from joblib import wrap_non_picklable_objects

#import pyprind
from tqdm import tqdm_notebook as tqdm

try :
    import pyslurm
    HAS_PYSLURM = True
except ImportError :
    HAS_PYSLURM = False

cell_template = '''
import pickle

{% for module in params['modules'] -%}
import {{ module }}
{% endfor %}

{% for name, value in params['input_vars'].items() %}
{{ name }} = pickle.loads( {{ value }} )
{% endfor %}

{{ code_cell }}

_output = {}
{% for var in params['output_vars'] %}
_output['{{ var }}'] = {{ var }}
{%- endfor %}
pickle.dump( _output, open( '{{ params['output_pickle'] }}', 'wb' ) )
print( 'code cell completed.')
'''

slurm_template = '''#!/bin/bash
#
#SBATCH --job-name=undead_test
#SBATCH --output=undead_test.txt
#
#SBATCH --ntasks={{ cpus }}
#SBATCH --time=10:00
#SBATCH --mem-per-cpu=100

{% for cell_script in cell_scripts %}
srun {{ interpreter }} {{ cell_script }}
{%- endfor %}
'''

### BEGIN : monkeypatch for joblib borrowed from
###         https://gist.github.com/MInner/12f9cf961059aed1a60e72c5531a697f

def text_progessbar(seq, total=None):
    step = 1
    tick = time.time()
    while True :
        time_diff = time.time() - tick
        avg_speed = time_diff/step
        total_str = 'of %n' % total if total else ''
        print( 'step', step, '%.2f' % time_diff, 'avg: %.2f iter/sec' % avg_speed, total_str )
        step += 1
        yield next( seq )

all_bar_funcs = {
    'tqdm'  : lambda args : lambda x : tqdm( x, **args ),
    'txt'   : lambda args : lambda x : text_progessbar( x, **args ),
    'False' : lambda args : iter,
    'None'  : lambda args : iter,
}

def ParallelExecutor( use_bar='tqdm', **joblib_args ) :
    def aprun( bar=use_bar, **tq_args ) :
        def tmp( op_iter ) :
            if str( bar ) in all_bar_funcs.keys():
                bar_func = all_bar_funcs[ str(bar) ]( tq_args )
            else:
                raise ValueError( 'Value %s not supported as bar type' % bar )
            return Parallel( **joblib_args )( bar_func( op_iter ) )
        return tmp
    return aprun

### END borrowed code

@wrap_non_picklable_objects
class Undead :
    '''Helper class to assist with execution.'''
    
    def __init__( self, code_cell, scratch=None, debug=False ) :
        self.code_cell  = code_cell
        self.debug      = debug
        self.template   = cell_template
        #self.scratch    = TemporaryDirectory( dir=scratch )
        self.scratch    = scratch

    def shuffle( self, run_params ) :
        '''Locally executes a code cell with given run parameters.'''
        
        stdout, stderr = self._execute( self.code_cell, run_params )
        return stdout, stderr, run_params
    
    def moan( self, run_params ) :
        '''Creates a temporary file for a code cell and returns the name.'''
        
        T = Template( self.template )
        
        run_params['output_pickle'] = NamedTemporaryFile( mode='w',
                                                          suffix='.output', 
                                                          dir=self.scratch,
                                                          delete=False ).name
        
        # generate the cell-script from the template
        with NamedTemporaryFile( mode='w', suffix='.cell',
                                 dir=self.scratch, delete=False ) as f :
            f.write( T.render( params    = run_params,
                               code_cell = self.code_cell ) )
            
            return f.name, run_params
    
    def _execute( self, cell_code, run_params ) :
        '''Execute the cell code.'''
        
        cell_script, run_params = self.moan( run_params )
        
        # execute the cell
        p = subprocess.Popen( [ 'python', str(cell_script) ],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE )
        
        # returns tuple (stdout, stderr)
        return p.communicate()

@magics_class
class SummonUndead( Magics ) :
    
    def __init__( self, shell=None, **kwargs ) :
        super( SummonUndead, self ).__init__( shell, **kwargs )
        self.shell = shell
    
    @cell_magic
    @magic_arguments()
    @argument( '-l', '--label',   type=str,        help='Job label.'                             )
    @argument( '-n', '--cpus',    type=int,        help='Number of CPUs to use.'                 )
    @argument( '-i', '--params',  type=str,        help='Vector of input parameters.'            )
    @argument( '-o', '--output',  action='append', help='Vector of output parameters.'           )
    @argument( '-s', '--scratch', type=str,        help='Scratch directory (required for slurm)' )
    @argument( '-d', '--debug',   type=bool,       help='Enable debugging output.',
               default=False )
    @argument( '-m', '--mode',    type=str,        help='Execution mode.',
               default='local_serial' )
    def moan( self, line, cell ) :
        '''Command the zombies to moan horribly.'''
        
        args = parse_argstring( self.moan, line )

        
        # input should be a list of dictionaries
        params = [] 
        if args.params :
            try :
                user_input = self.shell.user_ns[ args.params ]
                
                if not isinstance( user_input, list ) :
                    raise NameError( 'Input vector must be a list of dictionaries.' )
                
                if len( user_input ) == 0 :
                    raise NameError( 'Input cannot be empty.' )
                
                if not isinstance( user_input[0], dict ) :
                    raise NameError( 'Input vector must be a list of dictionaries.' )
                
                # populate the params vector with pickled inputs
                for run in user_input :
                    run_params = {}
                    run_params['input_vars'] = {}
                    for key, value in run.items() :
                        run_params['input_vars'][ key ] = pickle.dumps( value )
                    params.append( run_params )
                
            except KeyError :
                raise NameError( "name '%s' is not defined" % args.input )
        
        # figure out what modules the user has loaded
        modules = set( key for key,value in self.shell.user_ns.items() if isinstance( value, types.ModuleType ) )
        modules = modules - set( [ '__builtin__', '__builtins__' ] )
        
        # populate the params vector with output variable names, 
        # paths to temporary files for pickled output, and the
        # module names
        for run_params in params :
            if args.output :
                run_params['output_vars'] = ','.join( args.output ).split( ',' )
            else :
                run_params['output_vars'] = []
                run_params['output_pickle'] = None
            run_params[ 'modules' ] = modules
        
        if args.debug :
            print( 'user_input :', user_input )
            print( 'params :', params )
        
        if not args.mode in [ 'local_serial', 'local_parallel', 'slurm' ] :
            raise NameError( 'Unknown execution mode : %s' % args.mode )
        
        if args.mode == 'local_serial' :
            output_vector = self._execute_local_serial( cell, params, debug=args.debug )
        elif args.mode == 'local_parallel' :
            output_vector = self._execute_local_parallel( cell, params, args.cpus, debug=args.debug )
        elif args.mode == 'slurm' :
            if not args.scratch :
                raise Exception( 'No scratch directory specified.' )
            output_vector = self._execute_slurm( cell, params, args.cpus,
                                                 scratch=args.scratch, job_name=args.label,
                                                 debug=args.debug )
        
        self.shell.push( { args.label + '_output' : output_vector } )
    
    @line_magic
    def summon_undead( self, line ) :
        
        return 'Army of undead summoned. ' 
   
    def _execute_slurm( self, code_cell, params, cpus, 
                        scratch=None, job_name='undead', 
                        debug=False ) :
        '''Execute code cell through slurm.'''
        
        if not HAS_PYSLURM :
            raise Exception( 'pyslurm not installed.' )
        
        undead = Undead( code_cell, scratch=scratch, debug=debug )
        
        T = Template( slurm_template )
    
        cell_scripts, params = list( zip( *[ undead.moan(p) for p in params ] ) )
        
        slurm_submit_script_path = undead.scratch + '/submit.sh'
        
        with open( slurm_submit_script_path, 'w' ) as f :
            f.write( T.render( interpreter  = 'python',
                               cpus         = cpus, 
                               cell_scripts = cell_scripts ) )
        
        job_command = 'bash ' + slurm_submit_script_path
            
        job_args = { 'wrap'        : job_command,
                     'job_name'    : job_name,
                     'ntasks'      : cpus,
                     'time'        : '10:00',
                     'mem_per_cpu' : 100,
                     'chdir'       : undead.scratch }
            
        job = pyslurm.job().submit_batch_job( job_args )
        
        print( 'job id', job, 'submitted' )
        
        return params

    def _execute_local_serial( self, cell_code, params, scratch=None, debug=False ) :
        '''Execute code cell locally without concurrency (cpus argument is ignored).'''
        
        undead = Undead( cell_code, scratch=scratch, debug=debug )
        #progbar = pyprind.ProgBar( len(params), title='executing in local serial mode...' )
        
        output_vector = []
        with tqdm( total=len( params ) ) as progbar :
            for n,p in enumerate( params ) :
                progbar.update()
                
                stdout, stderr, run_params = undead.shuffle( p )
                
                if debug :
                    print( 'stdout {} :'.format(n), stdout )
                    print( 'stderr {} :'.format(n), stderr )
            
                run_output = pickle.load( open( p['output_pickle'], 'rb' ) ) 
                output_vector.append( run_output )
        
        return output_vector

    def _execute_local_parallel( self, code_cell, params, cpus, scratch=None, debug=False ) :
        '''Execute code cell locally with concurrency.'''
        
        undead = Undead( code_cell, scratch=scratch, debug=debug )
        aprun = ParallelExecutor( n_jobs=cpus )
        
        result = aprun( total=len(params) )(delayed( undead.shuffle )( p ) for p in params )
       
        if debug :
            for stdout, stderr in r :
                print( 'stdout :', stdout )
                print( 'stderr :', stderr )
        
        output_vector = []
        for stdout, stderr, p in result :
            
            run_output = pickle.load( open( p['output_pickle'], 'rb' ) )
            output_vector.append( run_output )
        
        return output_vector

def load_ipython_extension( ip ) :
    '''Load extension in IPython.'''
    summon_undead = SummonUndead( ip )
    ip.register_magics( summon_undead )
