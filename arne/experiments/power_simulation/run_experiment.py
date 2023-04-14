import sys
sys.path.append("../..")

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
import numpy as np
from aughs import ShrinkageClassifier, cross_val_shrinkage
from tqdm import trange
from argparse import ArgumentParser
import joblib



def simulate_categorical(n_samples: int, relevance: float):
    X = np.zeros((n_samples, 5))
    X[:, 0] = np.random.normal(0, 1, n_samples)
    n_categories = [2, 4, 10, 20]
    for i in range(1, 5):
        X[:, i] = np.random.choice(
            a=n_categories[i-1], size=n_samples,
            p=np.ones(n_categories[i - 1]) / n_categories[i - 1])
    y = np.zeros(n_samples)
    y[X[:, 1] == 0] = np.random.binomial(
        1, 0.5 - relevance, np.sum(X[:, 1] == 0))
    y[X[:, 1] == 1] = np.random.binomial(
        1, 0.5 + relevance, np.sum(X[:, 1] == 1))
    return X, y


def run_experiment(lambdas, relevances, shrink_modes, clf_type="rf"):
    relevances_str = ["{:.2f}".format(rel)[2:] for rel in relevances]
    result_importances = {rel: {sm: None for sm in shrink_modes}
                          for rel in relevances_str}
    result_scores = {rel: {sm: None for sm in shrink_modes}
                      for rel in relevances_str}
    for i, relevance in enumerate(relevances):
        rel_str = relevances_str[i]
        X, y = simulate_categorical(1000, relevance)

        # Compute importances for classical RF/DT
        if clf_type == "rf":
            clf = RandomForestClassifier().fit(X, y)
        elif clf_type == "dt":
            clf = DecisionTreeClassifier().fit(X, y)
        else:
            raise ValueError("Unknown classifier type")
        result_importances[rel_str]["no_shrinkage"] = clf.feature_importances_

        # Compute importances for different HS modes
        if clf_type == "rf":
            hsc = ShrinkageClassifier(RandomForestClassifier())
        elif clf_type == "dt":
            hsc = ShrinkageClassifier(DecisionTreeClassifier())
        else:
            raise ValueError("Unknown classifier type")

        for shrink_mode in ["hs", "hs_entropy", "hs_log_cardinality"]:
            param_grid = {"shrink_mode": [shrink_mode], "lmb": lambdas}
            lmb_scores = cross_val_shrinkage(
                hsc, X, y, param_grid, n_splits=5, n_jobs=1,
                return_param_values=False)
            result_scores[rel_str][shrink_mode] = lmb_scores
            best_idx = np.argmax(lmb_scores)
            best_lmb = lambdas[best_idx]
            hsc.set_shrink_params(shrink_mode=shrink_mode, lmb=best_lmb)
            result_importances[rel_str][shrink_mode] = hsc.estimator_.feature_importances_
    return result_importances, result_scores


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--n-replications", type=int, default=8)
    parser.add_argument("--importances-file", type=str,
                        default="output/importances.pkl")
    parser.add_argument("--clf-type", type=str, default="rf")
    parser.add_argument("--scores-file", type=str,
                        default="output/scores.pkl")
    parser.add_argument("--n-jobs", type=int, default=-1)
    args = parser.parse_args()

    lambdas = [0.1, 1.0, 10.0, 25.0, 50.0, 100.0]
    relevances = [0., 0.05, 0.1, 0.15, 0.2]
    relevances_str = ["{:.2f}".format(rel)[2:] for rel in relevances]
    shrink_modes = ["hs", "hs_entropy", "hs_log_cardinality"]

    results = joblib.Parallel(n_jobs=args.n_jobs, verbose=10)(
        joblib.delayed(run_experiment)(lambdas, relevances, shrink_modes,
                                       args.clf_type)
        for _ in range(args.n_replications))
    
    # Gather all results
    importances = {
        rel: {
            mode: [] for mode in shrink_modes + ["no_shrinkage"]}
        for rel in relevances_str
    }

    scores = {
        rel: {
            mode: [] for mode in shrink_modes}
        for rel in relevances_str
    }

    # Concatenate results
    for result_importances, result_scores in results:
        for rel in relevances_str:
            for mode in shrink_modes + ["no_shrinkage"]:
                importances[rel][mode].append(result_importances[rel][mode])
            for mode in shrink_modes:
                scores[rel][mode].append(result_scores[rel][mode])
    
    # Convert to numpy arrays
    for rel in relevances_str:
        for mode in shrink_modes + ["no_shrinkage"]:
            importances[rel][mode] = np.array(importances[rel][mode])
        for mode in shrink_modes:
            scores[rel][mode] = np.array(scores[rel][mode])

    # Save to disk
    joblib.dump(importances, args.importances_file)
    joblib.dump(scores, args.scores_file)