from youwol.app.environment import YouwolEnvironment
from youwol.app.routers.projects import IPipelineFactory, JsBundle, Link, Pipeline
from youwol.pipelines.pipeline_typescript_weback_npm import pipeline, PipelineConfig, PublishConfig
from youwol.utils.context import Context


class PipelineFactory(IPipelineFactory):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get(self, env: YouwolEnvironment, context: Context) -> Pipeline:
        publish_conf = PublishConfig(
            packagedFolders=["assets"],
            ignore=[
                "mkdocs-ts-doc/*",
                "**/.mypy_cache/*",
                "**/__pycache__/*",
                "**/*.egg-info/*",
                "**/mkdocs_py_griffe/build/*"
            ]
        )
        config = PipelineConfig(target=JsBundle(links=[
            Link(name="doc", url="dist/docs/index.html"),
            Link(name="coverage", url="coverage/lcov-report/index.html"),
            Link(name="bundle-analysis", url="dist/bundle-analysis.html")
        ]),publishConfig=publish_conf)
        return await pipeline(config, context)
