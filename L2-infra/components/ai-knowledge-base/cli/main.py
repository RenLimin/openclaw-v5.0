"""
AI KB CLI main entry
"""
import click
import sys
import os
from typing import Optional
import json

from ai_kb import AIKB
from ai_kb.api import AIKBService
from ai_kb.ingestion import IngestionPipeline
from ai_kb.template import TemplateManager


@click.group()
@click.option('--config', '-c', help='Configuration file path', default=None)
@click.pass_context
def cli(ctx, config):
    """AI Knowledge Base CLI"""
    ctx.ensure_object(dict)
    ctx.obj['config'] = config


# === Instance management ===

@cli.command(name='instance')
@click.argument('action', type=click.Choice(['create', 'list', 'show', 'delete', 'stats']))
@click.option('--code', '-i', help='Instance code')
@click.option('--name', '-n', help='Instance name')
@click.option('--template', '-t', help='Template to use for create')
@click.option('--description', '-d', help='Instance description')
@click.option('--db-path', help='Database path', default=None)
@click.pass_context
def instance(ctx, action, code, name, template, description, db_path):
    """Manage KB instances"""

    if action == 'create':
        if not code or not name or not template:
            click.echo("Error: code, name, template are required for create")
            sys.exit(1)

        if not db_path:
            # Default: ./data/{code}.db
            db_path = f"./data/{code}.db"

        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        kb = AIKB(db_path)
        kb.init_db()
        tm = TemplateManager(kb)
        domain_id = tm.create_instance_from_template(
            template,
            code,
            name,
            description
        )
        click.echo(f"Created instance {code} with domain ID {domain_id} at {db_path}")

    elif action == 'list':
        # TODO: implement
        click.echo("list instances not implemented yet")

    elif action == 'show':
        # TODO: implement
        click.echo("show instance not implemented yet")

    elif action == 'delete':
        # TODO: implement
        click.echo("delete instance not implemented yet")

    elif action == 'stats':
        if not code or not db_path:
            click.echo("Error: code and db-path required")
            sys.exit(1)
        service = AIKBService(db_path, code)
        stats = service.stats()
        click.echo(json.dumps(stats, indent=2))


# === Ingestion ===

@cli.command(name='ingest')
@click.argument('action', type=click.Choice(['upload', 'scan', 'tasks', 'status']))
@click.option('--db-path', help='Database path', required=True)
@click.option('--domain-code', '-d', help='Domain code', required=True)
@click.option('--file', '-f', help='File to upload', default=None)
@click.option('--dir', '-D', help='Directory to scan', default=None)
@click.option('--collection-id', '-c', help='Collection ID to ingest into', default=None)
def ingest(action, db_path, domain_code, file, dir, collection_id):
    """Document ingestion operations"""
    kb = AIKB(db_path)
    kb.connect()

    # Get domain id
    cursor = kb.execute("SELECT id FROM domain WHERE code = ?", (domain_code,))
    row = cursor.fetchone()
    if not row:
        click.echo(f"Error: domain {domain_code} not found")
        sys.exit(1)
    domain_id = row[0]

    pipeline = IngestionPipeline(kb)

    if action == 'upload':
        if not file:
            click.echo("Error: file required for upload")
            sys.exit(1)
        result = pipeline.ingest_single_file(
            domain_id,
            file,
            collection_id=collection_id
        )
        click.echo(json.dumps({
            "success": result.success,
            "doc_id": result.doc_id,
            "chunks_created": result.chunks_created,
            "quality_score": result.quality_score,
            "issues": result.issues,
            "error": result.error
        }, indent=2))

    elif action == 'scan':
        if not dir:
            click.echo("Error: directory required for scan")
            sys.exit(1)
        result = pipeline.scan_directory(
            domain_id,
            dir,
            collection_id=collection_id,
            on_result=lambda path, res: click.echo(f"{path}: {'OK' if res.success else f'FAILED - {res.error}'}")
        )
        click.echo(json.dumps(result, indent=2))

    elif action == 'tasks':
        # TODO: implement
        click.echo("list tasks not implemented yet")

    elif action == 'status':
        # TODO: implement
        click.echo("task status not implemented yet")


# === Query ===

@cli.command(name='query')
@click.argument('question')
@click.option('--db-path', help='Database path', required=True)
@click.option('--domain-code', '-d', help='Domain code', required=True)
@click.option('--top-k', '-k', help='Number of results', default=5)
@click.option('--format', '-f', type=click.Choice(['json', 'markdown']), default='markdown')
@click.option('--include-expired', help='Include expired entities', is_flag=True)
def query(question, db_path, domain_code, top_k, format, include_expired):
    """Query the knowledge base"""
    service = AIKBService(db_path, domain_code, include_expired=include_expired)
    result = service.query(question, top_k=top_k, format=format)
    if format == 'markdown':
        click.echo(result.get('markdown', json.dumps(result, indent=2)))
    else:
        click.echo(json.dumps(result, indent=2))


# === Entity management ===

@cli.command(name='entity')
@click.argument('action', type=click.Choice(['list', 'show', 'expire']))
@click.option('--db-path', help='Database path', required=True)
@click.option('--domain-code', '-d', help='Domain code', required=True)
@click.option('--id', '-i', help='Entity ID', type=int, default=None)
@click.option('--collection-id', '-c', help='Collection ID', type=int, default=None)
@click.option('--status', '-s', help='Filter by status', default=None)
def entity(action, db_path, domain_code, id, collection_id, status):
    """Entity management operations"""
    service = AIKBService(db_path, domain_code)

    if action == 'list':
        entities = service.list_entities(collection_id, status)
        click.echo(json.dumps(entities, indent=2))

    elif action == 'show':
        if not id:
            click.echo("Error: entity id required")
            sys.exit(1)
        ent = service.get_entity(id)
        click.echo(json.dumps(ent, indent=2))

    elif action == 'expire':
        if not id:
            click.echo("Error: entity id required")
            sys.exit(1)
        result = service.mark_entity_expired(id)
        click.echo(json.dumps(result, indent=2))


# === Feedback management ===

@cli.command(name='feedback')
@click.argument('action', type=click.Choice(['submit', 'stats', 'list-low']))
@click.option('--db-path', help='Database path', required=True)
@click.option('--domain-code', '-d', help='Domain code', required=True)
@click.option('--query', help='Query text', default=None)
@click.option('--type', 'feedback-type', type=click.Choice(['useful', 'not_useful', 'incorrect']), default=None)
@click.option('--entity-id', type=int, default=None)
@click.option('--threshold', help='Negative feedback threshold', default=1)
def feedback(action, db_path, domain_code, query, feedback_type, entity_id, threshold):
    """Feedback management"""
    service = AIKBService(db_path, domain_code)

    if action == 'submit':
        if not query or not feedback_type:
            click.echo("Error: query and feedback-type required")
            sys.exit(1)
        result = service.add_feedback(query, feedback_type, entity_id=entity_id)
        click.echo(json.dumps(result, indent=2))

    elif action == 'stats':
        if not entity_id:
            click.echo("Error: entity-id required")
            sys.exit(1)
        result = service.get_entity_feedback_stats(entity_id)
        click.echo(json.dumps(result, indent=2))

    elif action == 'list-low':
        result = service.list_low_score_knowledge(threshold)
        click.echo(json.dumps(result, indent=2))


# === Template management ===

@cli.command(name='template')
@click.argument('action', type=click.Choice(['list', 'show', 'create']))
@click.option('--db-path', help='Database path', required=True)
@click.option('--id', help='Template ID', default=None)
@click.option('--file', '-f', help='YAML template file to create/update', default=None)
def template(action, db_path, id, file):
    """Template management"""
    kb = AIKB(db_path)
    kb.connect()
    tm = TemplateManager(kb)

    if action == 'list':
        templates = tm.list_templates()
        result = [t.to_dict() for t in templates]
        click.echo(json.dumps(result, indent=2))

    elif action == 'show':
        if not id:
            click.echo("Error: template id required")
            sys.exit(1)
        t = tm.get_template(id)
        if not t:
            click.echo(f"Template {id} not found")
            sys.exit(1)
        click.echo(json.dumps(t.to_dict(), indent=2))

    elif action == 'create':
        if not file or not os.path.exists(file):
            click.echo("Error: valid template file required")
            sys.exit(1)
        with open(file, 'r') as f:
            yaml_content = f.read()
        template_id = os.path.splitext(os.path.basename(file))[0]
        if id:
            template_id = id
        t = Template.from_yaml(template_id, yaml_content)
        tm.save_template(t)
        click.echo(f"Saved template {template_id} version {t.version}")


# === Health ===

@cli.command()
@click.option('--db-path', help='Database path', required=True)
def health(db_path):
    """Check database health"""
    try:
        kb = AIKB(db_path)
        kb.connect()
        version = kb.get_current_migration_version()
        click.echo(f"OK: database connected, current migration version {version}")
    except Exception as e:
        click.echo(f"FAILED: {e}")
        sys.exit(1)


# === Serve ===

@cli.command()
@click.option('--host', default='0.0.0.0', help='Host to bind')
@click.option('--port', default=8000, help='Port to bind')
@click.option('--config', help='Config file path', required=True)
def serve(host, port, config):
    """Start REST API server"""
    # Import here to avoid circular imports
    from ai_kb.api.server import run_server
    run_server(host, port, config)


def main():
    cli(obj={})


if __name__ == '__main__':
    main()
