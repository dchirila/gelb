#!/usr/bin/env python3
"""
Auto-generated script to create GeLB AST class hierarchy diagram using matplotlib.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch
import numpy as np

def create_class_diagram():
    """Create a visual class diagram of the GeLB AST hierarchy."""
    fig, ax = plt.subplots(1, 1, figsize=(20, 15))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_aspect('equal')
    
    # Category positions and colors
    categories = {
        "Abstract Base Classes": {"pos": (10, 80), "nodes": 12, "color": "C0"},
        "Other Nodes": {"pos": (35, 80), "nodes": 3, "color": "C1"},
        "Statement Nodes": {"pos": (60, 80), "nodes": 10, "color": "C2"},
        "Block Nodes": {"pos": (85, 80), "nodes": 6, "color": "C3"},
        "Terminal Nodes": {"pos": (10, 60), "nodes": 9, "color": "C4"},
        "Selection Nodes": {"pos": (35, 60), "nodes": 3, "color": "C5"},
        "Data Type Nodes": {"pos": (60, 60), "nodes": 2, "color": "C6"},
        "Expression Nodes": {"pos": (85, 60), "nodes": 16, "color": "C7"},
    }
    
    # Draw category boxes
    for category, info in categories.items():
        x, y = info["pos"]
        color = info["color"]
        node_count = info["nodes"]
        
        # Draw box
        box = FancyBboxPatch((x-8, y-3), 16, 6, 
                           boxstyle="round,pad=0.1",
                           facecolor=color, alpha=0.3,
                           edgecolor=color, linewidth=2)
        ax.add_patch(box)
        
        # Add text
        ax.text(x, y+1, category, ha='center', va='center', fontsize=10, fontweight='bold')
        ax.text(x, y-1, f"{node_count} nodes", ha='center', va='center', fontsize=8)
    
    # Add title and labels
    ax.set_title("GeLB AST Node Categories Overview", fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel("Node Categories Distribution", fontsize=12)
    ax.set_ylabel("Inheritance Hierarchy", fontsize=12)
    
    # Remove axes
    ax.set_xticks([])
    ax.set_yticks([])
    
    # Add statistics text
    stats_text = f"""
    Total Nodes: 61
    Abstract: 1
    Concrete: 60
    Max Depth: 5
    Avg Fields: 0.8
    """
    ax.text(80, 15, stats_text, fontsize=10, bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.8))
    
    plt.tight_layout()
    return fig

if __name__ == "__main__":
    fig = create_class_diagram()
    plt.savefig("gelb_ast_overview.png", dpi=300, bbox_inches='tight')
    plt.savefig("gelb_ast_overview.pdf", bbox_inches='tight')
    print("📊 Class diagram saved as gelb_ast_overview.png and gelb_ast_overview.pdf")
    plt.show()
