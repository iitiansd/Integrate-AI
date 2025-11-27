#!/usr/bin/env python3
"""
AST Function Flow Sample
-----------------------
This module demonstrates the use of Python's ast module to analyze
function definitions and their call relationships in Python code.
"""

import ast
import os
import sys
from typing import Dict, List, Set, Tuple, Optional
import networkx as nx
import matplotlib.pyplot as plt


def parse_code_to_ast(code: str) -> ast.Module:
    """
    Parse Python code string into an Abstract Syntax Tree.
    
    Args:
        code: String containing Python code
        
    Returns:
        The AST representation of the code
    """
    try:
        return ast.parse(code)
    except SyntaxError as e:
        print(f"Syntax error in code: {e}")
        return None


def extract_function_definitions(tree: ast.Module) -> Dict[str, ast.FunctionDef]:
    """
    Extract all function definitions from an AST.
    
    Args:
        tree: AST module to analyze
        
    Returns:
        Dictionary mapping function names to their AST nodes
    """
    functions = {}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions[node.name] = node
            
    return functions


def find_function_calls(tree: ast.Module) -> List[Tuple[Optional[str], str]]:
    """
    Find all function calls in the AST and identify their callers.
    
    Args:
        tree: AST module to analyze
        
    Returns:
        List of (caller_name, called_name) tuples
    """
    calls = []
    current_function = None
    
    class FunctionCallVisitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            nonlocal current_function
            old_function = current_function
            current_function = node.name
            self.generic_visit(node)
            current_function = old_function
            
        def visit_Call(self, node):
            if isinstance(node.func, ast.Name):
                calls.append((current_function, node.func.id))
            self.generic_visit(node)
    
    FunctionCallVisitor().visit(tree)
    return calls


def build_call_graph(functions: Dict[str, ast.FunctionDef], 
                     calls: List[Tuple[Optional[str], str]]) -> nx.DiGraph:
    """
    Build a directed graph representing function call relationships.
    
    Args:
        functions: Dictionary of function definitions
        calls: List of (caller, callee) tuples
        
    Returns:
        NetworkX DiGraph representing the call graph
    """
    graph = nx.DiGraph()
    
    # Add all functions as nodes
    for func_name in functions:
        graph.add_node(func_name)
    
    # Add edges for function calls
    for caller, callee in calls:
        if caller and callee in functions:
            graph.add_edge(caller, callee)
    
    return graph


def visualize_call_graph(graph: nx.DiGraph, output_file: str = None) -> None:
    """
    Visualize the function call graph.
    
    Args:
        graph: NetworkX DiGraph representing the call graph
        output_file: Optional file path to save the visualization
    """
    plt.figure(figsize=(12, 8))
    pos = nx.spring_layout(graph)
    nx.draw(graph, pos, with_labels=True, node_color='lightblue', 
            node_size=1500, arrows=True, arrowsize=15)
    
    if output_file:
        plt.savefig(output_file)
    plt.show()


def analyze_function_complexity(functions: Dict[str, ast.FunctionDef]) -> Dict[str, int]:
    """
    Analyze the complexity of each function based on AST node count.
    
    Args:
        functions: Dictionary of function definitions
        
    Returns:
        Dictionary mapping function names to their complexity scores
    """
    complexity = {}
    
    for name, node in functions.items():
        # Count the number of nodes in the function's AST
        node_count = sum(1 for _ in ast.walk(node))
        complexity[name] = node_count
    
    return complexity


def find_unused_functions(functions: Dict[str, ast.FunctionDef], 
                         calls: List[Tuple[Optional[str], str]]) -> Set[str]:
    """
    Find functions that are defined but never called.
    
    Args:
        functions: Dictionary of function definitions
        calls: List of (caller, callee) tuples
        
    Returns:
        Set of unused function names
    """
    called_functions = {callee for _, callee in calls}
    all_functions = set(functions.keys())
    
    return all_functions - called_functions


def dfs_traversal(graph: nx.DiGraph, start_node: str) -> List[str]:
    """
    Perform a depth-first search traversal of the call graph starting from a given node.
    
    Args:
        graph: NetworkX DiGraph representing the call graph
        start_node: The node to start the DFS traversal from
        
    Returns:
        List of nodes in the order they were visited
    """
    visited = set()
    result = []
    
    def dfs(node):
        if node not in visited:
            visited.add(node)
            result.append(node)
            for neighbor in graph.neighbors(node):
                dfs(neighbor)

    dfs(start_node)
    return result


def analyze_code_file(file_path: str) -> nx.DiGraph:
    """
    Analyze a Python file and display its function call graph.
    
    Args:
        file_path: Path to the Python file to analyze
        
    Returns:
        NetworkX DiGraph representing the call graph
    """
    try:
        with open(file_path, 'r') as f:
            code = f.read()
        
        # Parse code to AST
        tree = parse_code_to_ast(code)
        if not tree:
            return None
        
        # Extract function definitions and calls
        functions = extract_function_definitions(tree)
        calls = find_function_calls(tree)
        
        # Build and visualize call graph
        graph = build_call_graph(functions, calls)
        
        # Analyze function complexity
        complexity = analyze_function_complexity(functions)
        
        # Find unused functions
        unused = find_unused_functions(functions, calls)
        
        # Print results
        print(f"Found {len(functions)} functions in {file_path}")
        print(f"Function complexity:")
        for func, score in sorted(complexity.items(), key=lambda x: x[1], reverse=True):
            print(f"  {func}: {score}")
        
        if unused:
            print(f"Unused functions: {', '.join(unused)}")
        
        # Visualize the call graph
        visualize_call_graph(graph)
        
        return graph
        
    except Exception as e:
        print(f"Error analyzing file {file_path}: {e}")
        return None


if __name__ == "__main__":
    # Example usage
    if len(sys.argv) > 1:
        graph = analyze_code_file(sys.argv[1])
        if graph:
            # Perform DFS traversal on the call graph starting from a specific function
            start_function = 'get_progress_data'  # Change this to the desired starting function
            dfs_result = dfs_traversal(graph, start_function)
            print(f"DFS traversal starting from {start_function}: {dfs_result}")
    else:
        # Self-analysis: analyze this file itself
        graph = analyze_code_file(__file__)
        if graph:
            # Perform DFS traversal on the call graph starting from a specific function
            start_function = 'get_progress_data'  # Change this to the desired starting function
            dfs_result = dfs_traversal(graph, start_function)
            print(f"DFS traversal starting from {start_function}: {dfs_result}")
