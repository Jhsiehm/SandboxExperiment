"""Fixed one-attempt residual calibration; callers provide fitting rows only."""
import numpy as np
from scipy.optimize import minimize
from scipy.special import softmax


class FitFailure(RuntimeError):
    def __init__(self, diagnostics):
        self.diagnostics=diagnostics
        super().__init__('Fixed SLSQP fit failed: '+str(diagnostics))


def validated(initial,targets,logits,groups):
    initial=np.asarray(initial)
    targets=np.asarray(targets)
    logits=np.asarray(logits,dtype=np.float64)
    groups=np.asarray(groups,dtype=str)
    if initial.dtype.kind=='b' or targets.dtype.kind=='b':
        raise ValueError('Boolean categories are invalid')
    if initial.ndim!=1 or targets.shape!=initial.shape or groups.shape!=initial.shape or logits.shape!=(len(initial),6) or not len(initial):
        raise ValueError('Malformed fitting arrays')
    if not (np.isfinite(initial).all() and np.isfinite(targets).all() and np.isfinite(logits).all()):
        raise ValueError('Nonfinite fitting data')
    if not (np.equal(initial,np.floor(initial)).all() and np.equal(targets,np.floor(targets)).all() and
            ((1<=initial)&(initial<=6)).all() and ((1<=targets)&(targets<=6)).all()):
        raise ValueError('Expected integer categories1..6')
    return initial.astype(int),targets.astype(int),logits,groups


def transition_table(initial,targets):
    counts=np.ones((6,6),dtype=np.float64)
    for before,after in zip(initial,targets):
        counts[int(before)-1,int(after)-1]+=1
    return counts/counts.sum(axis=1,keepdims=True)


def group_weights(groups):
    unique,counts=np.unique(groups,return_counts=True)
    return np.asarray([1/(len(unique)*counts[np.searchsorted(unique,g)]) for g in groups])


def objective_and_gradient(theta,log_prior,centered_logits,targets,weights,extension):
    b=theta[:6]
    alpha=theta[6] if extension else 0.0
    p=softmax(log_prior+b[None,:]+alpha*centered_logits,axis=1)
    truth=(targets[:,None]<=np.arange(1,6)[None,:]).astype(float)
    error=np.cumsum(p,axis=1)[:,:5]-truth
    objective=np.sum(weights*np.mean(error**2,axis=1))+.01*np.mean(b**2)+(.01*alpha**2 if extension else 0)
    dprob=np.zeros_like(p)
    dprob[:,:5]=(2/5)*np.flip(np.cumsum(np.flip(error,axis=1),axis=1),axis=1)
    dlogits=p*(dprob-np.sum(dprob*p,axis=1,keepdims=True))*weights[:,None]
    gb=dlogits.sum(axis=0)+(2*.01/6)*b
    gradient=np.concatenate([gb,[np.sum(dlogits*centered_logits)+.02*alpha]]) if extension else gb
    if not np.isfinite(objective) or not np.isfinite(gradient).all():
        raise FitFailure({'success':False,'reason':'nonfinite objective or gradient','attempts':1})
    return float(objective),gradient


def fit(initial,targets,logits,groups,*,extension):
    initial,targets,logits,groups=validated(initial,targets,logits,groups)
    if type(extension) is not bool:
        raise ValueError('extension must be boolean')
    table=transition_table(initial,targets)
    log_prior=np.log(table[initial-1])
    z=logits-logits.mean(axis=1,keepdims=True)
    weights=group_weights(groups)
    dimensions=7 if extension else 6
    constraint_gradient=np.r_[np.ones(6),0.] if extension else np.ones(6)
    initial_objective=objective_and_gradient(np.zeros(dimensions),log_prior,z,targets,weights,extension)[0]
    result=minimize(objective_and_gradient,np.zeros(dimensions),args=(log_prior,z,targets,weights,extension),
        jac=True,method='SLSQP',bounds=[(-2.,2.)]*6+([(0.,1.)] if extension else []),
        constraints=[{'type':'eq','fun':lambda x:float(x[:6].sum()),'jac':lambda x:constraint_gradient}],
        options={'maxiter':500,'ftol':1e-9,'disp':False})
    theta=np.asarray(result.x)
    final_gradient=np.asarray(getattr(result,'jac',np.full(dimensions,np.nan)))
    diagnostics=dict(success=bool(result.success),status=int(result.status),message=str(result.message),
                     iterations=int(result.nit),objective=float(result.fun),method='SLSQP',attempts=1,
                     maxiter=500,ftol=1e-9,initialization='all zeros',initial_objective=initial_objective,
                     final_gradient_norm=float(np.linalg.norm(final_gradient)) if np.isfinite(final_gradient).all() else None)
    feasible=(theta.shape==(dimensions,) and final_gradient.shape==(dimensions,) and np.isfinite(final_gradient).all() and np.isfinite(theta).all() and np.isfinite(result.fun) and
              abs(theta[:6].sum())<=1e-7 and (np.abs(theta[:6])<=2+1e-7).all() and
              (not extension or -1e-7<=theta[6]<=1+1e-7))
    if not result.success or not feasible:
        diagnostics['feasible']=bool(feasible)
        raise FitFailure(diagnostics)
    penalty=.01*np.mean(theta[:6]**2)+(.01*theta[6]**2 if extension else 0.)
    diagnostics.update(final_regularization=float(penalty),final_group_mean_rps=float(result.fun-penalty))
    return dict(table=table.tolist(),bias=theta[:6].tolist(),alpha=float(theta[6]) if extension else 0.,
                extension=extension,optimizer=diagnostics,fit_people=len(initial),fit_groups=len(set(groups)),
                fit_group_ids=sorted(set(groups)))


def predict(model,initial,logits):
    initial=np.asarray(initial)
    logits=np.asarray(logits,dtype=np.float64)
    if initial.ndim!=1 or logits.shape!=(len(initial),6) or not np.isfinite(logits).all():
        raise ValueError('Malformed prediction input')
    if not (np.isfinite(initial).all() and np.equal(initial,np.floor(initial)).all() and ((1<=initial)&(initial<=6)).all()):
        raise ValueError('Invalid initial category')
    table=np.asarray(model['table'],dtype=np.float64)
    bias=np.asarray(model['bias'],dtype=np.float64)
    alpha=float(model['alpha'])
    if table.shape!=(6,6) or bias.shape!=(6,) or not np.isfinite(table).all() or not np.isfinite(bias).all() or not np.isfinite(alpha) or (table<=0).any():
        raise ValueError('Invalid fitted model')
    p=softmax(np.log(table[initial.astype(int)-1])+bias[None,:]+alpha*(logits-logits.mean(axis=1,keepdims=True)),axis=1)
    if not np.isfinite(p).all() or not np.allclose(p.sum(axis=1),1,rtol=0,atol=1e-12):
        raise ValueError('Invalid calibrated probabilities')
    return p


def rps_by_group(probabilities,targets,groups):
    p=np.asarray(probabilities,dtype=np.float64)
    y=np.asarray(targets)
    groups=np.asarray(groups,dtype=str)
    if (p.shape!=(len(y),6) or groups.shape!=y.shape or not len(y) or not np.isfinite(p).all() or
        (p<0).any() or (p>1).any() or not np.allclose(p.sum(axis=1),1,rtol=0,atol=1e-6)):
        raise ValueError('Invalid scoring arrays')
    if not (np.isfinite(y).all() and np.equal(y,np.floor(y)).all() and ((1<=y)&(y<=6)).all()):
        raise ValueError('Invalid scoring targets')
    values=np.mean((np.cumsum(p,axis=1)[:,:5]-(y[:,None]<=np.arange(1,6)[None,:]))**2,axis=1)
    return {str(g):float(values[groups==g].mean()) for g in sorted(set(groups))}
