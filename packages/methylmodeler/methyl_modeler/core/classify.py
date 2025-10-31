
import math

def log_beta(a,b):
    from math import lgamma
    return lgamma(a) + lgamma(b) - lgamma(a+b)

def log_pdf_beta(x,a,b):
    return (a-1)*math.log(x) + (b-1)*math.log(1-x) - log_beta(a,b)

def classify(sample, panel, priors=(0.5,0.5)):
    logL_C = math.log(priors[0])
    logL_H = math.log(priors[1])
    for i, x in enumerate(sample):
        aC,bC,aH,bH = panel[i]
        logL_C += log_pdf_beta(x,aC,bC)
        logL_H += log_pdf_beta(x,aH,bH)
    # Compute posterior
    max_log = max(logL_C, logL_H)
    denom = math.exp(logL_C - max_log) + math.exp(logL_H - max_log)
    P_C = math.exp(logL_C - max_log) / denom
    P_H = 1 - P_C
    return P_C, P_H
