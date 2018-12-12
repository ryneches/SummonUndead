from distutils.core import setup

README = open( 'README.md' ).read()

setup(
    author           = 'Russell Y. Neches',
    author_email     = 'ryneches@lbl.gov',
    description      = 'Summons an army of undead.',
    long_description = README,
    name             = 'SummonUndead',
    py_modules       = [ 'SummonUndead' ],
    requires         = [ 'ipython' ],
    version          = '0.1'
)