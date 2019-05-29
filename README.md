# SummonUndead

Sometimes, when you're up in your Tower of Necromancy working on some evil,
raising and leading armies of undead horrors on relatively small missions 
can be a real drag on your productivity. `SummonUndead` takes the hassle out 
of work-a-day necromantic battle magic, leaving you more time to focus on
mentoring your mid-tier bosses, dungeon management, and other big-picture
problems.

### Installing

`SummonUndead` requires the following Python modules :

* [Jupyter](https://jupyter.org/)
* [jinja2](http://jinja.pocoo.org/)
* [joblib](https://joblib.readthedocs.io/en/latest/)
* [tqmd](https://github.com/tqdm/tqdm)
* [pyslurm](https://pyslurm.github.io/)

Note that `pyslurm` [has some packaging issues](https://github.com/PySlurm/pyslurm/issues/102) that
appear to still be a problem, so you may have to install it directly from its GitHub repo :

```
$ git clone https://github.com/PySlurm/pyslurm.git
$ cd pyslurm
$ git checkout 18.08.0 # skip this step if your site uses slurm version 17.11
$ python ./setup.py build
$ python ./setup.py install
```
