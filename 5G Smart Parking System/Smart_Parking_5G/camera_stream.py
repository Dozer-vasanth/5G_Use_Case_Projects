from stream_engine import StreamEngine, RuntimeConfig


# Feature 18: Backward-compatible stream module delegating to new engine
def generate_frames():
    engine = StreamEngine(RuntimeConfig())
    for frame in engine.generate_frames():
        yield frame