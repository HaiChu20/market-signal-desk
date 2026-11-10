"""Small fixed classifiers with geometric log-odds offset and later-fold calibration."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.special import expit, logit
from sklearn.isotonic import IsotonicRegression
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
import lightgbm as lgb

from .dataset import FORBIDDEN

EPS=1e-6

def baseline(p0):return np.asarray(p0,float)

class ResidualModel:
    def __init__(self,kind='lightgbm',features=None):
        self.kind=kind;self.features=None if features is None else tuple(features);self.model=None;self.calibrator=None
    def _matrix(self,frame,fit=False):
        raw=frame.reindex(columns=self.features).to_numpy(dtype=np.float32)
        if self.kind=='lightgbm':return raw
        if fit:
            self.imputer=SimpleImputer(strategy='median',keep_empty_features=True).fit(raw)
            self.scaler=StandardScaler().fit(self.imputer.transform(raw))
        return self.scaler.transform(self.imputer.transform(raw))
    def fit(self,frame):
        if self.features is None:
            forbidden=FORBIDDEN|{'ts','known_at','feature_known_at','deadline_ts','side','price','sl','tp',
                'planned_risk','p0','SL_R','TP_R','cost_R','financing_R','spread_R'}
            first=frame.groupby('sym').known_at.transform('min') if 'sym' in frame else frame.known_at.min()
            warm=frame.loc[frame.known_at>=first+pd.Timedelta(days=30)]
            if warm.empty:warm=frame
            self.features=tuple(c for c in frame if c not in forbidden and
                pd.api.types.is_numeric_dtype(frame[c]) and warm[c].notna().mean()>=.5)
        if not self.features:
            self.model=None;return self
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
                'max_depth':3,'min_data_in_leaf':100,'feature_fraction':.5,
                'lambda_l2':10,'verbosity':-1,
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
            raw=self.predict(frame,False)
            self.calibrator=IsotonicRegression(y_min=0,y_max=1,out_of_bounds='clip').fit(raw,frame.tp_first)
            bins=np.clip((raw*20).astype(int),0,19)
            counts=pd.DataFrame({'bin':bins,'event_key':frame.event_key.to_numpy() if 'event_key' in frame else np.arange(len(frame))})
            self.bin_counts=counts.groupby('bin').event_key.nunique().reindex(range(20),fill_value=0).to_numpy()
        return self

    def uncertainty(self,frame):
        p=self.predict(frame)
        if self.calibrator is None:
            return np.sqrt(p*(1-p)/10)
        bins=np.clip((self.predict(frame,False)*20).astype(int),0,19)
        # Distinct events, rather than the many correlated candidate pairs,
        # define the calibration-bin effective sample size.
        n=np.maximum(self.bin_counts[bins],10)
        return np.sqrt(p*(1-p)/n)


def fit_time_ordered(train,kind='lightgbm',features=None):
    train=train.sort_values('known_at')
    cut=int(.8*len(train))
    # Purge labels crossing into the later calibration fold.
    cal=train.iloc[cut:]
    fit=train.iloc[:cut]
    fit=fit[fit.label_end_ts<cal.known_at.min()]
    model=ResidualModel(kind,features).fit(fit)
    model.calibrate(cal)
    return model
