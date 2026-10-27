import importlib.util
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.optimize._numdiff import approx_derivative

spec=importlib.util.spec_from_file_location('residual_solver',Path(__file__).parents[1]/'scripts/residual_calibration_solver.py')
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def example():
    initial=np.array([1,2,3,4,5,6]*2)
    target=np.array([1,2,4,4,5,6,2,2,3,5,5,6])
    logits=np.arange(72,dtype=float).reshape(12,6)/50
    groups=np.array(['a']*4+['b']*4+['c']*4)
    return initial,target,logits,groups


@pytest.mark.parametrize('extension',[False,True])
def test_analytic_gradient_matches_finite_difference(extension):
    initial,target,logits,groups=example()
    prior=np.log(m.transition_table(initial,target)[initial-1])
    z=logits-logits.mean(axis=1,keepdims=True)
    weights=m.group_weights(groups)
    theta=np.array([.1,-.2,.3,-.1,.0,-.1]+([.4] if extension else []))
    value,grad=m.objective_and_gradient(theta,prior,z,target,weights,extension)
    numeric=approx_derivative(lambda t:m.objective_and_gradient(t,prior,z,target,weights,extension)[0],theta,method='3-point')
    np.testing.assert_allclose(grad,numeric,atol=1e-8,rtol=1e-6)
    assert np.isfinite(value)


def test_fit_single_fixed_attempt_and_probabilities():
    initial,target,logits,groups=example()
    model=m.fit(initial,target,logits,groups,extension=True)
    assert model['optimizer']['success'] and model['optimizer']['attempts']==1
    assert model['optimizer']['maxiter']==500 and model['optimizer']['ftol']==1e-9
    assert abs(sum(model['bias']))<1e-7 and 0<=model['alpha']<=1
    p=m.predict(model,initial,logits)
    np.testing.assert_allclose(p.sum(axis=1),1,atol=1e-12)
    shifted=m.predict(model,initial,logits+np.arange(12)[:,None]*100)
    np.testing.assert_allclose(p,shifted,atol=1e-12)


def test_table_uses_only_supplied_subset():
    initial,target,logits,groups=example()
    model=m.fit(initial[:4],target[:4],logits[:4],groups[:4],extension=False)
    expected=np.ones((6,6))
    for x,y in zip(initial[:4],target[:4]):
        expected[x-1,y-1]+=1
    expected/=expected.sum(axis=1,keepdims=True)
    np.testing.assert_allclose(model['table'],expected)
    assert model['fit_people']==4 and model['fit_groups']==1


def test_failure_has_no_retry(monkeypatch):
    calls=[]
    def fail(*args,**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(x=np.zeros(6),success=False,status=9,message='iteration limit',nit=500,fun=.2)
    monkeypatch.setattr(m,'minimize',fail)
    with pytest.raises(m.FitFailure) as failure:
        m.fit(*example(),extension=False)
    assert len(calls)==1 and failure.value.diagnostics['attempts']==1


def test_equal_group_weights_and_ordinal_rps():
    weights=m.group_weights(np.array(['a','a','a','b']))
    assert weights==pytest.approx([1/6,1/6,1/6,1/2])
    p=np.array([[1,0,0,0,0,0],[0,0,0,0,0,1]])
    assert m.rps_by_group(p,[6,6],['a','b'])=={'a':1.,'b':0.}


def test_nonfinite_input_rejected():
    initial,target,logits,groups=example()
    logits[0,0]=np.nan
    with pytest.raises(ValueError,match='Nonfinite'):
        m.fit(initial,target,logits,groups,extension=True)
