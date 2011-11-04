"""
Generalized additive models



Requirements for smoothers
--------------------------

smooth(y, weights=xxx) : ? no return ? alias for fit
predict(x=None) : smoothed values, fittedvalues or for new exog
df_fit() : degress of freedom of fit ?


"""

# JP:
# changes: use PolySmoother instead of crashing bspline
# TODO: check/catalogue required interface of a smoother
# TODO: replace default smoother by corresponding function to initialize
#       other smoothers
# TODO: fix iteration, don't define class with iterator methods, use looping;
#       add maximum iteration and other optional stop criteria
# fixed some of the dimension problems in PolySmoother,
#       now graph for example looks good
# NOTE: example script is now in examples folder

import numpy as np

from scikits.statsmodels.genmod.families import family
from scikits.statsmodels.sandbox.nonparametric.smoothers import PolySmoother as SmoothingSpline   # relative import
from scikits.statsmodels.genmod.generalized_linear_model import GLM


def default_smoother(x):
#    _x = x.copy()
#    _x.sort()
    _x = np.sort(x)
    n = x.shape[0]
    # taken form smooth.spline in R

    #if n < 50:
    if n < 500:
        nknots = n
    else:
        a1 = np.log(50) / np.log(2)
        a2 = np.log(100) / np.log(2)
        a3 = np.log(140) / np.log(2)
        a4 = np.log(200) / np.log(2)
        if n < 200:
            nknots = 2**(a1 + (a2 - a1) * (n - 50)/150.)
        elif n < 800:
            nknots = 2**(a2 + (a3 - a2) * (n - 200)/600.)
        elif n < 3200:
            nknots = 2**(a3 + (a4 - a3) * (n - 800)/2400.)
        else:
            nknots = 200 + (n - 3200.)**0.2
    knots = _x[np.linspace(0, n-1, nknots).astype(np.int32)]

    #s = SmoothingSpline(knots, x=x.copy())
    order = 3 #what about knots? need smoother *args or **kwds
    s = SmoothingSpline(order, x=x.copy())
#    s.gram(d=2)
#    s.target_df = 5
    return s

class Offset(object):

    def __init__(self, fn, offset):
        self.fn = fn
        self.offset = offset

    def __call__(self, *args, **kw):
        return self.fn(*args, **kw) + self.offset

class Results(object):

    def __init__(self, Y, alpha, exog, smoothers, family, offset):
        self.nobs, self.k_vars = exog.shape  #assumes exog is 2d
        #weird: If I put the previous line after the definition of self.mu,
        #    then the attributed don't get added
        self.Y = Y
        self.alpha = alpha
        self.smoothers = smoothers
        self.offset = offset
        self.family = family
        self.exog = exog
        self.offset = offset
        self.mu = self.linkinverse(exog)  #TODO: remove __call__



    def __call__(self, exog):
        '''expected value ? check new GLM, same as mu for given exog
        maybe remove this
        '''
        return self.linkinverse(exog)

    def linkinverse(self, exog):  #TODO what's the name in GLM
        '''expected value ? check new GLM, same as mu for given exog
        '''
        return self.family.link.inverse(self.predict(exog))

    def predict(self, exog):
        '''predict response, sum of smoothed components
        TODO: What's this in the case of GLM, corresponds to X*beta ?
        '''
        #note: sum is here over axis=0,
        #TODO: transpose in smoothed and sum over axis=1

        #BUG: there is some inconsistent orientation somewhere
        #temporary hack, won't work for 1d
        #print dir(self)
        print 'self.nobs, self.k_vars', self.nobs, self.k_vars
        exog_smoothed = self.smoothed(exog)
        print 'exog_smoothed.shape', exog_smoothed.shape
        if exog_smoothed.shape[0] == self.k_vars:
            return np.sum(self.smoothed(exog), axis=0) + self.alpha
        if exog_smoothed.shape[1] == self.k_vars:
            return np.sum(exog_smoothed, axis=1) + self.alpha
        else:
            raise ValueError('shape mismatch in predict')

    def smoothed(self, exog):
        '''get smoothed prediction for each component

        '''
        #bug: with exog in predict I get a shape error
        print 'smoothed', exog.shape, self.smoothers[0].predict(exog).shape
        return np.array([self.smoothers[i].predict(exog) + self.offset[i]
                         for i in range(exog.shape[1])])

class AdditiveModel(object):
    '''additive model with non-parametric, smoothed components

    Parameters
    ----------
    '''

    def __init__(self, exog, smoothers=None, weights=None):
        self.exog = exog
        if not weights is None:
            self.weights = weights
        else:
            self.weights = np.ones(self.exog.shape[0])

        self.smoothers = smoothers or [default_smoother(exog[:,i]) for i in range(exog.shape[1])]
        for i in range(exog.shape[1]):
            self.smoothers[i].df = 10
        self.family = family.Gaussian()

    def _iter__(self):
        '''initialize iteration ?, should be removed

        '''
        self.iter = 0
        self.dev = np.inf
        return self

    def next(self):
        '''internal calculation for one fit iteration
        '''
        _results = self.results
        Y = self.results.Y
        mu = _results.predict(self.exog)
        #TODO offset is not used ?
        offset = np.zeros(self.exog.shape[1], np.float64)
        alpha = (Y * self.weights).sum() / self.weights.sum()
        for i in range(self.exog.shape[1]):
            tmp = self.smoothers[i].predict()
            #TODO: check what smooth needs to do
            self.smoothers[i].smooth(Y - alpha - mu + tmp,
                                     weights=self.weights)
            tmp2 = self.smoothers[i].predict()
            offset[i] = -(tmp2*self.weights).sum() / self.weights.sum()
            mu += tmp2 - tmp

        #print self.iter
        #self.iter += 1 #missing incrementing of iter counter NOT
        return Results(Y, alpha, self.exog, self.smoothers, self.family, offset)

    def cont(self, tol=1.0e-04):
        '''condition to continue iteration loop

        Parameters
        ----------
        tol

        Returns
        -------
        cont : bool
            If true, then iteration should be continued.

        '''
        self.iter += 1 #moved here to always count, not necessary
        print self.iter, self.results.Y.shape,
        print self.results.predict(self.exog).shape, self.weights.shape
        curdev = (((self.results.Y - self.results.predict(self.exog))**2) * self.weights).sum()

        if self.iter > 30: #kill it, no max iterationoption
            return False
        if np.fabs((self.dev - curdev) / curdev) < tol:
            self.dev = curdev
            return False

        #self.iter += 1
        self.dev = curdev
        return True

    def df_resid(self):
        return self.results.Y.shape[0] - np.array([self.smoothers[i].df_fit() for i in range(self.exog.shape[1])]).sum()

    def estimate_scale(self):
        #TODO: remove use of self.results.__call__
        return ((self.results.Y - self.results(self.exog))**2).sum() / self.df_resid()

    def fit(self, Y):
        #iter(self)  # what does this do? anything?
        self._iter__()
        mu = 0
        alpha = (Y * self.weights).sum() / self.weights.sum()

        offset = np.zeros(self.exog.shape[1], np.float64)

        for i in range(self.exog.shape[1]):
            self.smoothers[i].smooth(Y - alpha - mu,
                                     weights=self.weights)
            tmp = self.smoothers[i].predict()
            offset[i] = (tmp * self.weights).sum() / self.weights.sum()
            tmp -= tmp.sum()
            mu += tmp

        self.results = Results(Y, alpha, self.exog, self.smoothers, self.family, offset)

        while self.cont():
            self.results = self.next()

        return self.results

class Model(GLM, AdditiveModel):
#class Model(AdditiveModel):
    #TODO: what does GLM do? Is it actually used ?
    #only used in __init__, dropping it doesn't change results
    #but where gets family attached now? - weird, it's Gaussian in this case now
    #also where is the link defined?
    #AdditiveModel overwrites family and sets it to Gaussian

    niter = 2

#    def __init__(self, exog, smoothers=None, family=family.Gaussian()):
#        GLM.__init__(self, exog, family=family)
#        AdditiveModel.__init__(self, exog, smoothers=smoothers)
#        self.family = family
    def __init__(self, endog, exog, smoothers=None, family=family.Gaussian()):
        print family
        self.family = family
        #TODO: inconsistent super __init__
        AdditiveModel.__init__(self, exog, smoothers=smoothers)
        GLM.__init__(self, endog, exog, family=family)
        print self.family

    def next(self):
        _results = self.results; Y = _results.Y
        if np.isnan(self.weights).all(): print "nanweights1"
        _results.mu = self.family.link.inverse(_results.predict(self.exog))
        weights = self.family.weights(_results.mu)
        if np.isnan(weights).all():
            self.weights = weights
            print "nanweights2"
        Z = _results.predict(self.exog) + self.family.link.deriv(_results.mu) * (Y - _results.mu)
        m = AdditiveModel(self.exog, smoothers=self.smoothers, weights=self.weights)

        #TODO: I don't know what the next two lines do, Z, Y ? which is endog?
        _results = m.fit(Z)
        _results.Y = Y
        _results.mu = self.family.link.inverse(_results.predict(self.exog))
        self.iter += 1
        self.results = _results

        return _results

    def estimate_scale(self, Y=None):
        """
        Return Pearson\'s X^2 estimate of scale.
        """

        if Y is None:
            Y = self.Y
        resid = Y - self.results.mu
        return (np.power(resid, 2) / self.family.variance(self.results.mu)).sum() / AdditiveModel.df_resid(self)

    def fit(self, Y):
        self.Y = np.asarray(Y, np.float64)

        #iter(self)
        self._iter__()

        #TODO code duplication with next?
        alpha = self.Y.mean()
        Z = self.family.link(alpha) + self.family.link.deriv(alpha) * (Y - alpha)
        m = AdditiveModel(self.exog, smoothers=self.smoothers)
        self.results = m.fit(Z)
        self.results.mu = self.family.link.inverse(self.results.predict(self.exog))
        self.results.Y = Y

        while self.cont():
            self.results = self.next()
            self.scale = self.results.scale = self.estimate_scale()


        return self.results
