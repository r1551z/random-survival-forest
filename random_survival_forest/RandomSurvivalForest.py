import numpy as np
import pandas as pd
from .SurvivalTree import SurvivalTree
from .scoring import concordance_index
from joblib import Parallel, delayed
import multiprocessing


class RandomSurvivalForest:
    bootstrap_idxs = None
    bootstraps = []
    oob_idxs = None
    oob_score = None
    trees = []
    random_states = []

    def __init__(self, n_estimators=2, min_leaf=3, unique_deaths=3, timeline=None, n_jobs=None, random_state=None):
        """
        A Random Survival Forest is a prediction model especially designed for survival analysis.
        :param n_estimators: The numbers of trees in the forest.
        :param timeline: The timeline used for the prediction.
        :param min_leaf: The minimum number of samples required to be at a leaf node. A split point at any depth will
        only be considered if it leaves at least min_leaf training samples in each of the left and right branches.
        :param unique_deaths: The minimum number of unique deaths required to be at a leaf node.
        :param n_jobs: The number of jobs to run in parallel for fit. None means 1.
        """
        self.n_estimators = n_estimators
        self.min_leaf = min_leaf
        self.timeline = timeline
        self.unique_deaths = unique_deaths
        self.n_jobs = n_jobs
        self.random_state = random_state

    def fit(self, x, y):
        """
        Build a forest of trees from the training set (X, y).
        :param x: The input samples. Should be a Dataframe with the shape [n_samples, n_features].
        :param y: The target values as a Dataframe with the survival time in the first column and the event
        in the second with the shape [n_samples, 2]
        :return: self: object
        """

        if self.n_jobs == -1:
            self.n_jobs = multiprocessing.cpu_count()
        elif self.n_jobs is None:
            self.n_jobs = 1
            #rz: change 32 to 31 so it won't cause high out of bounds error in python32
        self.random_states = np.random.RandomState(seed=self.random_state).randint(0, 2**31-1, self.n_estimators)
        self.bootstrap_idxs = self.draw_bootstrap_samples(x)

        trees = Parallel(n_jobs=self.n_jobs)(delayed(self.create_tree)(x, y, i) for i in range(self.n_estimators))


        for i in range(len(trees)):
            if trees[i].prediction_possible is True:
                self.trees.append(trees[i])
                self.bootstraps.append(self.bootstrap_idxs[i])

        self.oob_score = self.compute_oob_score(x, y)

        return self

    def create_tree(self, x, y, i):
        """
        Grows a survival tree for the bootstrap samples.
        :param y: label data frame y with survival time as the first column and event as second
        :param x: feature data frame x
        :param i: Indices
        :return: SurvivalTree
        """
        n_features = int(round(np.sqrt(x.shape[1]), 0))
        if self.random_state is None:
            f_idxs = np.random.permutation(x.shape[1])[:n_features]
        else:
            f_idxs = np.random.RandomState(seed=self.random_states[i]).permutation(x.shape[1])[:n_features]

        tree = SurvivalTree(x=x.iloc[self.bootstrap_idxs[i], :], y=y.iloc[self.bootstrap_idxs[i], :],
                            f_idxs=f_idxs, n_features=n_features, timeline=self.timeline,
                            unique_deaths=self.unique_deaths, min_leaf=self.min_leaf,
                            random_state=self.random_states[i])

        return tree

    def compute_oob_ensembles(self, x):
        """
        Compute OOB ensembles.
        :return: List of oob ensemble for each sample.
        """
        oob_ensemble_chfs = []
        for sample_idx in range(x.shape[0]):
            denominator = 0
            numerator = 0
            for b in range(len(self.trees)):
                if sample_idx not in self.bootstraps[b]:
                    sample = x.iloc[sample_idx].to_list()
                    chf = self.trees[b].predict(sample)
                    denominator = denominator + 1
                    numerator = numerator + 1 * chf

            if denominator == 0:
                continue
            else:
                ensemble_chf = numerator/denominator
                oob_ensemble_chfs.append(ensemble_chf)
        return oob_ensemble_chfs

    def compute_oob_score(self, x, y):
        """
        Compute the oob score (concordance-index).
        :return: c-index of oob samples
        """
        oob_ensembles = self.compute_oob_ensembles(x)
        c = concordance_index(y_time=y.iloc[:, 0], y_pred=oob_ensembles, y_event=y.iloc[:, 1])
        return c

    def predict(self, xs):
        """
        Predict survival for xs.
        :param xs:The input samples
        :return: List of the predicted cumulative hazard functions.
        """
        preds = []
        for x in xs.values:
            chfs = []
            for q in range(len(self.trees)):
                chfs.append(self.trees[q].predict(x))
            preds.append(pd.concat(chfs).groupby(level=0).mean())
        return preds

    def draw_bootstrap_samples(self, data):
        """
        Draw bootstrap samples
        :param data: Data to draw bootstrap samples of.
        :return: Bootstrap indices for each of the trees
        """
        bootstrap_idxs = []
        for i in range(self.n_estimators):
            no_samples = len(data)
            data_rows = range(no_samples)
            if self.random_state is None:
                bootstrap_idx = np.random.choice(data_rows, no_samples)
            else:
                np.random.seed(self.random_states[i])
                bootstrap_idx = np.random.choice(data_rows, no_samples)
            bootstrap_idxs.append(bootstrap_idx)

        return bootstrap_idxs
