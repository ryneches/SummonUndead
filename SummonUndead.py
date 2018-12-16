from __future__ import print_function

from IPython.core.magic import Magics, magics_class, line_magic, cell_magic, line_cell_magic
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring

import pickle
from tempfile import NamedTemporaryFile 
from jinja2 import Template

import types

import subprocess
import time

import concurrent.futures

import pyprind

cell_template = '''
import pickle
from tempfile import NamedTemporaryFile

{% for module in modules -%}
import {{ module }}
{% endfor %}

{% for name, value in params.items() %}
{{ name }} = pickle.loads( {{ value }} )
{% endfor %}

{{ cell_code }}

_output = {}
{% for var in output['vars'] %}
_output['{{ var }}'] = {{ var }}
{%- endfor %}
pickle.dump( _output, open( '{{ output['pickle'] }}', 'wb' ) )
'''

@magics_class
class SummonUndead( Magics ) :
    
    def __init__( self, shell=None, **kwargs ) :
        super( SummonUndead, self ).__init__( shell, **kwargs )
        self.shell = shell
        self.cell_template = Template( cell_template )
    
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
    
        print(args)

        # input should be a list of dictionaries
        input_vector = [] 
        if args.params :
            try :
                input_vector = self.shell.user_ns[ args.params ]
                
                if not isinstance( input_vector, list ) :
                    raise NameError( 'Input vector must be a list of dictionaries.' )
                
                if len( input_vector ) == 0 :
                    raise NameError( 'Input cannot be empty.' )
                
                if not isinstance( input_vector[0], dict ) :
                    raise NameError( 'Input vector must be a list of dictionaries.' )
                
                for run in input_vector :
                    for key, value in run.items() :
                        run[key] = pickle.dumps( value )
                
            except KeyError :
                raise NameError( "name '%s' is not defined" % args.input )
        
        if args.debug :
            print( 'input_vector :', input_vector )
        
        # get the user output variable names, create temp files for each
        output = {}
        if args.output :
            output[ 'vars' ] = ','.join( args.output ).split( ',' )
            output[ 'pickle' ] = NamedTemporaryFile( mode='w', suffix='.output', delete=False ).name
        
        if args.debug :
            print( 'output :', output )
        
        # figure out what modules the user has loaded
        modules = set( key for key,value in self.shell.user_ns.items() if isinstance( value, types.ModuleType ) )
        modules = modules - set( [ '__builtin__', '__builtins__' ] )
        
        if args.debug :
            print( 'modules :', modules )
        
        if not args.mode in [ 'local_serial', 'local_parallel' ] :
            raise NameError( 'Unknown execution mode : %s' % args.mode )
        
        if args.mode == 'local_serial' :
            output_vector = self._execute_local_serial(   cell, input_vector, output, modules, None,
                                                          debug=args.debug )
        elif args.mode == 'local_parallel' :
            output_vector = self._execute_local_parallel( cell, input_vector, output, modules, None,
                                                          debug=args.debug )

        self.shell.push( { args.label + '_output' : output_vector } )
    
    @line_magic
    def summon_undead( self, line ) :
        
        return 'Army of undead summoned. ' 
        
    def _execute( self, cell_code, params, output, modules ) :
        '''Execute the cell code.'''
        
        # generate the cell-script from the template
        with NamedTemporaryFile( mode='w', suffix='.cell', delete=False ) as f :
            f.write( self.cell_template.render( modules   = modules,
                                                params    = params,
                                                output    = output,
                                                cell_code = cell_code ) )
            
            cell_script = f.name
 
        # execute the cell
        p = subprocess.Popen( [ 'python', str(cell_script) ],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE )
        
        # returns tuple (stdout, stderr)
        return p.communicate()

    def _execute_local_serial( self, cell_code, params, output, modules, cpus, debug=False ) :
        '''Execute code cell locally without concurrency (cpus argument is ignored).'''
        
        prog = pyprind.ProgBar( len(params), title='executing in local serial mode...' )
        output_vector = []
        for n,p in enumerate( params ) :
            prog.update()
            
            stdout, stderr = self._execute( cell_code, p, output, modules )
            
            if debug :
                print( 'stdout {} :'.format(n), stdout )
                print( 'stderr {} :'.format(n), stderr )

            run_output = pickle.load( open( output['pickle'], 'rb' ) ) 
            output_vector.append( run_output )
        
        return output_vector

    def _execute_local_parallel( self, code_cell, params, output, modules, cpus, debug=False ) :
        '''Execute code cell locally with concurrency.'''
        
        args = [ ( code_cell, p, output, modules ) for p in params ]
        
        with concurrent.futures.ProcessPoolExecutor( max_workers=cpus ) as executor :
            executor.map( self._execute, args )
    
def load_ipython_extension( ip ) :
    '''Load extension in IPython.'''
    summon_undead = SummonUndead( ip )
    ip.register_magics( summon_undead )
