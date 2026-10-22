from shalf.pipelines import LocalRunner, Pipeline


def test_runs_in_dependency_order():
    pipeline = Pipeline("train")

    @pipeline.step(depends_on=["extract"])
    def train(extract):
        return extract + 1

    @pipeline.step()
    def extract():
        return 1

    assert LocalRunner().run(pipeline) == {"extract": 1, "train": 2}
