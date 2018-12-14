from __future__ import print_function

from IPython.core.magic import Magics, magics_class, line_magic, cell_magic, line_cell_magic
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring

import pickle
from tempfile import NamedTemporaryFile 
from jinja2 import Template

import types

import subprocess
import time

cell_template = '''
import pickle
from tempfile import NamedTemporaryFile

{% for module in modules -%}
import {{ module }}
{% endfor %}

{% for name, value in input.items() %}
{{ name }} = pickle.loads( {{ value }} )
{% endfor %}

{{ cell_code }}

{% for name, tmpfile in output.items() %}
pickle.dump( {{ name }}, open( '{{ tmpfile }}', 'wb' ) )
{%- endfor %}
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
    @argument( '-i', '--input',  type=str,        help='Vector of input parameters.'  )
    @argument( '-o', '--output', action='append', help='Vector of output parameters.' )
    def moan( self, line, cell ) :
        '''Command the zombies to moan horribly.'''
        
        args = parse_argstring( self.moan, line )
        
        # input should be a list of dictionaries
        input_vector = [] 
        if args.input :
            try :
                input_vector = self.shell.user_ns[ args.input ]
                
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
        
        # get the user output variable names, create temp files for each
        output = {}
        if args.output :
            for var in ','.join( args.output ).split( ',' ) :
                output[ var ] = NamedTemporaryFile( mode='w', suffix='.output', delete=False ).name
        
        # figure out what modules the user has loaded
        modules = set( key for key,value in self.shell.user_ns.items() if isinstance( value, types.ModuleType ) )
        modules = modules - set( [ '__builtin__', '__builtins__' ] )
        
        output_vector = []
        for input in input_vector :
            self._execute( cell, input, output, modules )
            run_output = {}
            for key, tmpfile in output.items() :
                run_output[ key ] = pickle.load( open( tmpfile, 'rb' ) )
            output_vector.append( run_output )

        self.shell.push( { args.label + '_output' : output_vector } )

    @line_magic
    def summon_undead( self, line ) :
        
        return 'Army of undead summoned. ' 

    def _execute( self, cell_code, input, output, modules ) :
        '''Execute the cell code.'''

        # generate the cell-script from the template
        with NamedTemporaryFile( mode='w', suffix='.cell', delete=False ) as f :
            f.write( self.cell_template.render( modules   = modules,
                                                input     = input,
                                                output    = output, 
                                                cell_code = cell_code ) )
            
            cell_script = f.name
 
        # execute the cell
        p = subprocess.Popen( [ 'python', str(cell_script) ],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE )
        stdout, stderr = p.communicate()


def load_ipython_extension( ip ) :
    '''Load extension in IPython.'''
    summon_undead = SummonUndead( ip )
    ip.register_magics( summon_undead )
