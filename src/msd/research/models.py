"""Small fixed classifiers with geometric log-odds offset and later-fold calibration."""
from __future__ import annotations
import numpy as np
from scipy.special import expit, logit
from sklearn.isotonic import IsotonicRegression
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
import lightgbm as lgb

from .dataset import FEATURES

EPS=1e-6

def baseline(p0):return np.asarray(p0,float)

class ResidualModel:
    def __init__(self,kind='lightgbm',features=FEATURES):
        self.kind=kind;self.features=tuple(features);self.model=None;self.calibrator=None
    def _matrix(self,frame,fit=False):
        raw=frame.reindex(columns=self.features).to_numpy(float)
        if fit:
            self.imputer=SimpleImputer(strategy='median',keep_empty_features=True).fit(raw)
            self.scaler=StandardScaler().fit(self.imputer.transform(raw))
        return self.scaler.transform(self.imputer.transform(raw))
    def fit(self,frame):
        x=self._matrix(frame,True);p=logit(np.clip(frame.p0.to_numpy(float),EPS,1-EPS));y=frame.tp_first.to_numpy(int)
        if len(np.unique(y))<2 or len(frame)<80:
            self.model=None;return self
        if self.kind=='logistic':
            # Treat logit(p0) as a fixed offset by fitting only residual features
            # to a pseudo-target via a regularized logistic solver with offset.
            from scipy.optimize import minimize
            def loss(w):
                z=p+x@w;pr=expit(z)
                return np.logaddexp(0,z).sum()-y@z+len(y)*np.dot(w,w)
            result=minimize(loss,np.zeros(x.shape[1]),jac=lambda w:x.T@(expit(p+x@w)-y)+2*len(y)*w,method='L-BFGS-B')
            self.model=result.x
        elif self.kind=='lightgbm':
            dataset=lgb.Dataset(x,label=y,init_score=p,free_raw_data=True)
            self.model=lgb.train({'objective':'binary','learning_rate':.03,'num_leaves':7,
                'max_depth':3,'min_data_in_leaf':100,'lambda_l2':10,'verbosity':-1,
                'num_threads':2},dataset,num_boost_round=40)
        else:raise ValueError(self.kind)
        return self
    def predict(self,frame,calibrated=True):
        p=logit(np.clip(frame.p0.to_numpy(float),EPS,1-EPS))
        if self.model is not None:
            x=self._matrix(frame)
            p+=x@self.model if self.kind=='logistic' else self.model.predict(x,raw_score=True)
        raw=expit(p)
        return self.calibrator.transform(raw) if calibrated and self.calibrator is not None else raw
    def calibrate(self,frame):
        if len(frame)>=20 and frame.tp_first.nunique()>1:
            self.calibrator=IsotonicRegression(y_min=0,y_max=1,out_of_bounds='clip').fit(self.predict(frame,False),frame.tp_first)
        return self


def fit_time_ordered(train,kind='lightgbm'):
    train=train.sort_values('known_at')
    cut=int(.8*len(train))
    # Purge labels crossing into the later calibration fold.
    cal=train.iloc[cut:]
    fit=train.iloc[:cut]
    fit=fit[fit.label_end_ts<cal.known_at.min()]
    model=ResidualModel(kind).fit(fit)
    model.calibrate(cal)
    return model
