from __future__ import print_function

from IPython.core.magic import Magics, magics_class, line_magic, cell_magic, line_cell_magic
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring

import pickle
from tempfile import NamedTemporaryFile 
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

cell_template = '''
import pickle
from tempfile import NamedTemporaryFile

{% for module in params['modules'] -%}
import {{ module }}
{% endfor %}

{% for name, value in params['input_vars'].items() %}
{{ name }} = pickle.loads( {{ value }} )
{% endfor %}

{{ cell_code }}

_output = {}
{% for var in params['output_vars'] %}
_output['{{ var }}'] = {{ var }}
{%- endfor %}
pickle.dump( _output, open( '{{ params['output_pickle'] }}', 'wb' ) )
'''


### BEGIN : code borrowed from
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
    
    def __init__( self, code_cell, debug=False ) :
        self.code_cell  = code_cell
        self.debug      = debug
        self.template   = cell_template
    
    def shuffle( self, run_params ) :
        
        return self._execute( self.code_cell, run_params )

    def _execute( self, cell_code, params ) :
        '''Execute the cell code.'''
        
        T = Template( self.template )
        
        # generate the cell-script from the template
        with NamedTemporaryFile( mode='w', suffix='.cell', delete=False ) as f :
            f.write( T.render( params    = params,
                               cell_code = cell_code ) )
            
            cell_script = f.name
        
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
    @argument( '-l', '--label',  type=str,        help='Job label.'                   )
    @argument( '-n', '--cpus',   type=int,        help='Number of CPUs to use.'       )
    @argument( '-i', '--params', type=str,        help='Vector of input parameters.'  )
    @argument( '-o', '--output', action='append', help='Vector of output parameters.' )
    @argument( '-d', '--debug',  type=bool,       help='Enable debugging output.',
               default=False )
    @argument( '-m', '--mode',   type=str,        help='Execution mode.',
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
                run_params['output_pickle'] = NamedTemporaryFile( mode='w', suffix='.output', delete=False ).name
            else :
                run_params['output_vars'] = []
                run_params['output_pickle'] = None
            run_params[ 'modules' ] = modules
        
        if args.debug :
            print( 'user_input :', user_input )
            print( 'params :', params )

        if not args.mode in [ 'local_serial', 'local_parallel' ] :
            raise NameError( 'Unknown execution mode : %s' % args.mode )
        
        if args.mode == 'local_serial' :
            output_vector = self._execute_local_serial( cell, params, debug=args.debug )
        elif args.mode == 'local_parallel' :
            output_vector = self._execute_local_parallel( cell, params, args.cpus, debug=args.debug )

        self.shell.push( { args.label + '_output' : output_vector } )
    
    @line_magic
    def summon_undead( self, line ) :
        
        return 'Army of undead summoned. ' 
    
    def _execute_local_serial( self, cell_code, params, debug=False ) :
        '''Execute code cell locally without concurrency (cpus argument is ignored).'''
        
        undead = Undead( cell_code, debug )
        #progbar = pyprind.ProgBar( len(params), title='executing in local serial mode...' )
        
        output_vector = []
        with tqdm( total=len( params ) ) as progbar :
            for n,p in enumerate( params ) :
                progbar.update()
                
                stdout, stderr = undead.shuffle( p )
                
                if debug :
                    print( 'stdout {} :'.format(n), stdout )
                    print( 'stderr {} :'.format(n), stderr )
            
                run_output = pickle.load( open( p['output_pickle'], 'rb' ) ) 
                output_vector.append( run_output )
        
        return output_vector

    def _execute_local_parallel( self, code_cell, params, cpus, debug=False ) :
        '''Execute code cell locally with concurrency.'''
        
        undead = Undead( code_cell, debug=debug )
        aprun = ParallelExecutor( n_jobs=cpus )

        r = aprun( total=len(params) )(delayed( undead.shuffle )( p ) for p in params )
        
        ## FIXME : make sure output from different runs doesn't end up being written to the
        ##         same pickle file
        
        if debug :
            for stdout, stderr in r :
                print( 'stdout :', stdout )
                print( 'stderr :', stderr )

        output_vector = []
        for p in params :

            run_output = pickle.load( open( p['output_pickle'], 'rb' ) )
            output_vector.append( run_output )

        return output_vector


def load_ipython_extension( ip ) :
    '''Load extension in IPython.'''
    summon_undead = SummonUndead( ip )
    ip.register_magics( summon_undead )
