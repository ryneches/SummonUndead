# SummonUndead

Summons an army of undead.

### Installing

`SummonUndead` requires the following Python modules :

* [Jupyter](https://jupyter.org/)
* [jinja2](http://jinja.pocoo.org/)
* [joblib](https://joblib.readthedocs.io/en/latest/)
* [tqmd](https://github.com/tqdm/tqdm)
* [pyslurm](https://pyslurm.github.io/)

Note that `pyslurm` [has some packaging issues](https://github.com/PySlurm/pyslurm/issues/102) that
appear to still be an issue, so you may have to install it directly from its GitHub repo :

```
$ git clone https://github.com/PySlurm/pyslurm.git
$ cd pyslurm
$ python ./setup.py build
$ python ./setup.py install
```
