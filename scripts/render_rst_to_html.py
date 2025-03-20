#!/usr/bin/env python3

"""
RST to HTML Renderer

This script monitors .rst files in the specified directories and renders them to HTML
whenever they change. It's useful for previewing documentation changes in real-time.

Usage:
    python render_rst_to_html.py [--dirs DIR1 DIR2 ...] [--interval SECONDS]

Options:
    --dirs        Directories to monitor for .rst files (default: project root and docs)
    --interval    Polling interval in seconds (default: 1.0)
"""

import os
import sys
import time
import hashlib
import click
from pathlib import Path
from datetime import datetime
from docutils.core import publish_file
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class RstFileHandler(FileSystemEventHandler):
    """Handles events for .rst files and renders them to HTML when they change."""
    
    def __init__(self):
        self.file_hashes = {}
        
    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith('.rst'):
            self.render_rst_to_html(event.src_path)
    
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.rst'):
            self.render_rst_to_html(event.src_path)
    
    def render_rst_to_html(self, rst_path):
        # Check if file content has actually changed using hash
        current_hash = self._get_file_hash(rst_path)
        if rst_path in self.file_hashes and self.file_hashes[rst_path] == current_hash:
            return
        
        self.file_hashes[rst_path] = current_hash
        
        # Generate HTML path from RST path
        html_path = os.path.splitext(rst_path)[0] + '.html'
        
        try:
            # Render RST to HTML
            publish_file(
                source_path=rst_path,
                destination_path=html_path,
                writer_name='html5'
            )
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] Rendered {os.path.basename(rst_path)} → {os.path.basename(html_path)}")
        except Exception as e:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] Error rendering {os.path.basename(rst_path)}: {str(e)}")
    
    def _get_file_hash(self, file_path):
        """Calculate MD5 hash of file contents"""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()


def scan_and_render_all(directories):
    """Scan all directories for .rst files and render them to HTML"""
    handler = RstFileHandler()
    for directory in directories:
        for rst_file in Path(directory).glob('**/*.rst'):
            handler.render_rst_to_html(str(rst_file))
    return handler


@click.command()
@click.option('--dirs', '-d', multiple=True, help='Directories to monitor for .rst files')
@click.option('--interval', '-i', type=float, default=1.0, help='Polling interval in seconds')
def main(dirs, interval):
    """Monitor and render .rst files to HTML whenever they change."""
    # Get project root directory
    project_root = Path(__file__).parent.parent
    
    # Default directories to monitor
    if dirs:
        directories = [os.path.abspath(d) for d in dirs]
    else:
        directories = [str(project_root), str(project_root / 'docs')]
    
    click.echo(click.style("RST to HTML Renderer", fg="green", bold=True))
    click.echo(click.style("====================\n", fg="green"))
    click.echo("Monitoring directories:")
    for directory in directories:
        click.echo(f"  - {directory}")
    click.echo(f"Polling interval: {interval} seconds\n")
    
    # Initial scan and render
    click.echo("Performing initial render of all .rst files...")
    handler = scan_and_render_all(directories)
    click.echo("Initial render complete.\n")
    
    # Set up watchdog observer
    observer = Observer()
    for directory in directories:
        observer.schedule(handler, directory, recursive=True)
    
    # Start monitoring
    click.echo("Monitoring for changes (press Ctrl+C to stop)...\n")
    observer.start()
    
    try:
        while True:
            time.sleep(interval)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
