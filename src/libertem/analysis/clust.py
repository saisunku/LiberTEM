from skimage.feature import peak_local_max
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.image import grid_to_graph
import numpy as np
import sparse
import inspect
import re

from libertem.viz import visualize_simple
from .base import BaseAnalysis, AnalysisResult, AnalysisResultSet
from libertem.utils.async_utils import run_blocking
from libertem.executor.base import JobCancelledError
from libertem.udf.masks import ApplyMasksUDF
from libertem.udf.base import UDFRunner
from libertem.udf.stddev import StdDevUDF, consolidate_result
from libertem import masks
from libertem.masks import _make_circular_mask
from .helper import GeneratorHelper


class ClusterTemplate(GeneratorHelper):

    short_name = "cluster"

    def __init__(self, params):
        self.params = params

    def format_code(self, code):
        code = re.sub(r"self\.|self, |self", "", code)
        # remove indentation
        code = code.split("\n")
        for idx, line in enumerate(code):
            code[idx] = line[4:]
        return "\n".join(code)

    def get_dependency(self):
        dep = [
           "from libertem.analysis import ClusterAnalysis",
           "from libertem.udf.stddev import StdDevUDF, consolidate_result",
           "from libertem.masks import _make_circular_mask",
           "from skimage.feature import peak_local_max",
           "import sparse",
           "from sklearn.feature_extraction.image import grid_to_graph",
           "from libertem.udf.masks import ApplyMasksUDF",
           "from sklearn.cluster import AgglomerativeClustering",
           "from libertem.analysis.base import AnalysisResult, AnalysisResultSet",
           "from libertem.viz import visualize_simple",
        ]
        return dep

    def temp_cluster_controller(self):
        temp_controller = [
                        "dataset = ds",
                        "roi, sd_udf_results = get_sd_results()",
                        "cluster_udf = get_cluster_udf(sd_udf_results)",
                        "udf_results = ctx.run_udf(dataset=ds, udf=cluster_udf, progress=True)",
                        "cluster_result = get_udf_results(udf_results, roi)",
        ]
        return '\n'.join(temp_controller)

    def get_docs(self):
        docs = ["# Cluster Analysis"]
        return '\n'.join(docs)

    def get_run_sd_udf(self):
        indent = " "*4
        temp_run_sd = [
            "def run_sd_udf(roi, stddev_udf):",
            f"{indent}sd_udf_results = ctx.run_udf(dataset=ds, udf=stddev_udf, roi=roi)",
            f"{indent}return roi, consolidate_result(sd_udf_results)"
        ]
        return "\n".join(temp_run_sd)

    def get_analysis(self):
        udf_results = self.format_code(inspect.getsource(ClusterAnalysis.get_udf_results))
        sd_roi = self.format_code(inspect.getsource(ClusterAnalysis.get_sd_roi))
        cluster_udf = self.format_code(inspect.getsource(ClusterAnalysis.get_cluster_udf))
        sd_results = self.format_code(inspect.getsource(ClusterAnalysis.get_sd_results))
        run_sd_udf = self.get_run_sd_udf()
        cluster_controller = self.temp_cluster_controller()

        temp_analysis = [
                    f"parameters={self.params}\ndataset=ds",
                    f"{sd_roi}",
                    f"{run_sd_udf}",
                    f"{sd_results}",
                    f"{cluster_udf}",
                    f"{udf_results}",
                    f"{cluster_controller}"
                    ]
        return '\n\n'.join(temp_analysis)

    def get_plot(self):
        plot = ["plt.figure()",
                "plt.imshow(cluster_result['intensity'].visualized)"]
        return ['\n'.join(plot)]


class ClusterAnalysis(BaseAnalysis, id_="CLUST"):
    TYPE = "UDF"

    def get_udf(self):
        # FIXME: we don't have all parameters available here to actually construct
        # a useful udf instance - this should be optional for Analysis subclasses
        # that implement the `controller` method
        return None

    def get_udf_results(self, udf_results, roi):
        n_clust = self.parameters["n_clust"]
        y, x = tuple(self.dataset.shape.nav)
        connectivity = grid_to_graph(
            # Transposed!
            n_x=y,
            n_y=x
        )
        f = udf_results['intensity'].raw_data
        feature_vector = f / np.abs(f).mean(axis=0)

        clustering = AgglomerativeClustering(
            affinity='euclidean', n_clusters=n_clust, linkage='ward',
            connectivity=connectivity
        ).fit(feature_vector)
        labels = np.array(clustering.labels_+1)
        return AnalysisResultSet([
            AnalysisResult(raw_data=udf_results['intensity'].data,
                           visualized=visualize_simple(
                               labels.reshape(self.dataset.shape.nav)),
                           key="intensity", title="intensity",
                           desc="result from integration over mask in Fourier space"),
        ])

    def get_sd_roi(self):
        if "roi" not in self.parameters:
            return None
        params = self.parameters["roi"]
        ny, nx = tuple(self.dataset.shape.nav)
        if params["shape"] == "rect":
            roi = masks.rectangular(
                params["x"],
                params["y"],
                params["width"],
                params["height"],
                nx, ny,
            )
        else:
            raise NotImplementedError("unknown shape %s" % params["shape"])
        return roi

    async def run_sd_udf(self, roi, stddev_udf):
        result_iter = UDFRunner([stddev_udf]).run_for_dataset_async(
            self.dataset, self.executor, roi=roi, cancel_id=self.cancel_id
        )
        async for (sd_udf_results,) in result_iter:
            pass
        if self.job_is_cancelled():
            raise JobCancelledError()
        return roi, consolidate_result(sd_udf_results)

    def get_sd_results(self):
        stddev_udf = StdDevUDF()
        roi = self.get_sd_roi()
        return self.run_sd_udf(roi, stddev_udf)

    def get_cluster_udf(self, sd_udf_results):

        center = (self.parameters["cy"], self.parameters["cx"])
        rad_in = self.parameters["ri"]
        rad_out = self.parameters["ro"]
        n_peaks = self.parameters["n_peaks"]
        min_dist = self.parameters["min_dist"]
        sstd = sd_udf_results['std']
        sshape = sstd.shape
        if not (center is None or rad_in is None or rad_out is None):
            mask_out = 1*_make_circular_mask(center[1], center[0], sshape[1], sshape[0], rad_out)
            mask_in = 1*_make_circular_mask(center[1], center[0], sshape[1], sshape[0], rad_in)
            mask = mask_out - mask_in
            masked_sstd = sstd*mask
        else:
            masked_sstd = sstd

        coordinates = peak_local_max(masked_sstd, num_peaks=n_peaks, min_distance=min_dist)

        y = coordinates[..., 0]
        x = coordinates[..., 1]
        z = range(len(y))

        mask = sparse.COO(
            shape=(len(y), ) + tuple(self.dataset.shape.sig),
            coords=(z, y, x), data=1
        )

        udf = ApplyMasksUDF(
            mask_factories=lambda: mask, mask_count=len(y), mask_dtype=np.uint8,
            use_sparse=True
        )
        return udf

    async def controller(self, cancel_id, executor, job_is_cancelled, send_results):

        self.cancel_id = cancel_id
        self.executor = executor
        self.job_is_cancelled = job_is_cancelled

        roi, sd_udf_results = await self.get_sd_results()
        udf = self.get_cluster_udf(sd_udf_results)

        result_iter = UDFRunner([udf]).run_for_dataset_async(
            self.dataset, executor, cancel_id=cancel_id
        )
        async for (udf_results,) in result_iter:
            pass

        if job_is_cancelled():
            raise JobCancelledError()

        results = await run_blocking(
            self.get_udf_results,
            udf_results=udf_results,
            roi=roi,
        )
        await send_results(results, True)

    @classmethod
    def get_template_helper(cls):
        return ClusterTemplate
