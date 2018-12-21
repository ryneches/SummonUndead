from distutils.core import setup

README = open( 'README.md' ).read()

setup(
    author           = 'Russell Y. Neches',
    author_email     = 'ryneches@lbl.gov',
    description      = 'Summons an army of undead.',
    long_description = README,
    name             = 'SummonUndead',
    py_modules       = [ 'SummonUndead' ],
    requires         = [ 'ipython', 'joblib', 'tqdm', 'jinja2' ],
    url              = 'https://github.com/ryneches/SummunUndead',
    version          = '0.1'
)
