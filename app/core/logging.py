import logging, sys, structlog
from app.core.config import settings

def setup_logging():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    structlog.configure(processors=[structlog.contextvars.merge_contextvars, structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()])

def setup_tracing(app, engine):
    from opentelemetry import trace
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    tp = TracerProvider(resource=Resource.create({"service.name": "eavie-api"}))
    if settings.OTLP_ENDPOINT:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.OTLP_ENDPOINT)))
    elif settings.APP_ENV != "production":
        tp.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(tp)
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
