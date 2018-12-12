from __future__ import print_function

from IPython.core.magic import Magics, magics_class, line_magic, cell_magic, line_cell_magic
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring

import pickle
from tempfile import NamedTemporaryFile 
from jinja2 import Template

import types

cell_template = '''
import pickle

{% for module in user_modules -%}
import {{ module }}
{% endfor %}

{% for input, data in input_arguments.items() %}
{{ input }} = {{ data }}
{% endfor %}

{{ cell_code }}

{% for output in output_arguments -%}
{{ output }}
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
    @argument( '-n', '--processes', type=int, help='Number of processes to launch.' )
    @argument( '-i', '--input',  action='append', help='Vector of input parameters.' )
    @argument( '-o', '--output', action='append', help='Vector of output parameters.' )
    def moan( self, line, cell ) :
        '''Command the zombies to moan horribly.'''
        
        args = parse_argstring( self.moan, line )
       
        # get the user input variables, pickle them, and stash them in a dictionary
        input_arguments = {}
        if args.input :
            for input in ','.join( args.input ).split( ',' ) :
                try :
                    val = self.shell.user_ns[ input ]
                    input_arguments[ input ] = pickle.dumps( val )
                except KeyError :
                    raise NameError( "name '%s' is not defined" % input )
        
        # get the user output variable names and stash them in a list
        output_arguments = []
        if args.output :
            for output in ','.join( args.output ).split( ',' ) :
                output_arguments.append( output )
        
        # figure out what modules the user has loaded
        user_modules = set( key for key,value in self.shell.user_ns.items() if isinstance( value, types.ModuleType ) )
        user_modules = user_modules - set( [ '__builtin__', '__builtins__' ] )
        
        # generate the cell-script from the template
        with NamedTemporaryFile( mode='w', suffix='.cell', delete=False ) as f :
            f.write( self.cell_template.render( user_modules     = user_modules,
                                                input_arguments  = input_arguments,
                                                output_arguments = output_arguments, 
                                                cell_code        = cell ) )
            return f.name                                                
 
        # put recovered output variables into the user's namespace
        #for output in output_arguments :        
        #    self.shell.push({output: output_ipy})
        
    @line_magic
    def summon_undead( self, line ) :
        return 'Army of undead summoned. ' 

def load_ipython_extension( ip ) :
    '''Load extension in IPython.'''
    summon_undead = SummonUndead( ip )
    ip.register_magics( summon_undead )