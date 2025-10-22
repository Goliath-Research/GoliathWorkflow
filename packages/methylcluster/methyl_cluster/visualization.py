"""
Visualization module for clustering results.

This module creates comprehensive visualizations of clustering results including
distance matrices, cluster trees, and dimensionality reduction projections.
"""

import numpy as np
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cluster import MethylCluster

logger = logging.getLogger(__name__)


class ClusterVisualizer:
    """
    Creates visualizations for clustering results.
    
    Generates:
    - Distance matrix heatmaps
    - HDBSCAN condensed tree plots
    - MDS projection plots
    - Cluster statistics plots
    """
    
    def __init__(self, cluster: 'MethylCluster'):
        """
        Initialize visualizer with clustering results.
        
        Args:
            cluster: MethylCluster instance with computed results
        """
        self.cluster = cluster
    
    def create_all_plots(self, output_dir: Path) -> None:
        """
        Generate all visualization plots.
        
        Args:
            output_dir: Directory to save plots
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Creating visualizations...")
        
        try:
            self.plot_distance_heatmap(output_dir)
        except Exception as e:
            logger.warning(f"Failed to create distance heatmap: {e}")
        
        try:
            self.plot_cluster_tree(output_dir)
        except Exception as e:
            logger.warning(f"Failed to create cluster tree: {e}")
        
        try:
            self.plot_mds_projection(output_dir)
        except Exception as e:
            logger.warning(f"Failed to create MDS projection: {e}")
        
        try:
            self.plot_cluster_statistics(output_dir)
        except Exception as e:
            logger.warning(f"Failed to create cluster statistics: {e}")
    
    def plot_distance_heatmap(self, output_dir: Path) -> None:
        """
        Create interactive heatmap of distance matrix.
        
        Args:
            output_dir: Directory to save plot
        """
        import plotly.graph_objects as go
        
        logger.info("Creating distance matrix heatmap...")
        
        # Create sample labels
        labels = [f"Sample {i}" for i in range(len(self.cluster.samples))]
        
        fig = go.Figure(data=go.Heatmap(
            z=self.cluster.distance_matrix,
            x=labels,
            y=labels,
            colorscale='Viridis',
            colorbar=dict(title='Distance')
        ))
        
        fig.update_layout(
            title=f'Distance Matrix Heatmap ({self.cluster.config.metric.value})<br>' +
                  f'{self.cluster.config.chrom}-{self.cluster.config.ctx}',
            xaxis_title='Sample',
            yaxis_title='Sample',
            width=800,
            height=800
        )
        
        output_file = output_dir / 'distance_heatmap.html'
        fig.write_html(str(output_file))
        logger.info(f"Saved distance heatmap to {output_file}")
    
    def plot_cluster_tree(self, output_dir: Path) -> None:
        """
        Create condensed tree visualization from HDBSCAN.
        
        Args:
            output_dir: Directory to save plot
        """
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        
        logger.info("Creating cluster tree plot...")
        
        if not hasattr(self.cluster.clusterer, 'condensed_tree_'):
            logger.warning("Condensed tree not available, skipping tree plot")
            return
        
        # Create the plot
        plt.figure(figsize=(12, 8))
        
        # Get number of clusters to determine if we should show selection
        n_clusters = len(set(self.cluster.cluster_labels)) - (1 if -1 in self.cluster.cluster_labels else 0)
        
        try:
            if n_clusters > 0:
                # Use matplotlib colormap instead of seaborn palette name
                import matplotlib.cm as cm
                # Create a colormap with enough colors
                colors = cm.get_cmap('Set1', max(n_clusters, 3))
                color_palette = [colors(i) for i in range(n_clusters)]
                
                self.cluster.clusterer.condensed_tree_.plot(
                    select_clusters=True,
                    selection_palette=color_palette
                )
            else:
                # No clusters, just plot the tree without selection
                self.cluster.clusterer.condensed_tree_.plot(
                    select_clusters=False
                )
        except Exception as e:
            # Fallback: plot without cluster selection
            logger.debug(f"Could not plot with cluster selection: {e}, plotting without selection")
            self.cluster.clusterer.condensed_tree_.plot(
                select_clusters=False
            )
        
        plt.title(f'HDBSCAN Cluster Tree\n{self.cluster.config.chrom}-{self.cluster.config.ctx}')
        
        output_file = output_dir / 'cluster_tree.png'
        plt.savefig(str(output_file), dpi=300, bbox_inches='tight')
        plt.close()
        logger.info(f"Saved cluster tree to {output_file}")
    
    def plot_mds_projection(self, output_dir: Path) -> None:
        """
        Create MDS projection of samples colored by cluster.
        
        Args:
            output_dir: Directory to save plot
        """
        import plotly.graph_objects as go
        from sklearn.manifold import MDS
        
        logger.info("Creating MDS projection...")
        
        # Perform MDS
        mds = MDS(n_components=2, dissimilarity='precomputed', random_state=42)
        coords = mds.fit_transform(self.cluster.distance_matrix)
        
        # Prepare data for plotting
        cluster_labels = self.cluster.cluster_labels
        unique_labels = sorted(set(cluster_labels))
        
        # Create traces for each cluster
        fig = go.Figure()
        
        for label in unique_labels:
            mask = cluster_labels == label
            cluster_name = 'Noise' if label == -1 else f'Cluster {label}'
            
            fig.add_trace(go.Scatter(
                x=coords[mask, 0],
                y=coords[mask, 1],
                mode='markers',
                name=cluster_name,
                marker=dict(
                    size=10,
                    opacity=0.7,
                    line=dict(width=1, color='white')
                ),
                text=[f"Sample {i}" for i in np.where(mask)[0]],
                hovertemplate='%{text}<br>x: %{x:.3f}<br>y: %{y:.3f}<extra></extra>'
            ))
        
        fig.update_layout(
            title=f'MDS Projection of Samples<br>{self.cluster.config.chrom}-{self.cluster.config.ctx}',
            xaxis_title='MDS Dimension 1',
            yaxis_title='MDS Dimension 2',
            width=900,
            height=700,
            hovermode='closest'
        )
        
        output_file = output_dir / 'mds_projection.html'
        fig.write_html(str(output_file))
        logger.info(f"Saved MDS projection to {output_file}")
    
    def plot_cluster_statistics(self, output_dir: Path) -> None:
        """
        Create bar chart of cluster sizes and statistics.
        
        Args:
            output_dir: Directory to save plot
        """
        import plotly.graph_objects as go
        
        logger.info("Creating cluster statistics plot...")
        
        # Count samples per cluster
        unique_labels = sorted(set(self.cluster.cluster_labels))
        cluster_names = []
        cluster_sizes = []
        
        for label in unique_labels:
            count = int(np.sum(self.cluster.cluster_labels == label))
            if label == -1:
                cluster_names.append('Noise')
            else:
                cluster_names.append(f'Cluster {label}')
            cluster_sizes.append(count)
        
        # Create bar chart
        fig = go.Figure(data=[
            go.Bar(
                x=cluster_names,
                y=cluster_sizes,
                text=cluster_sizes,
                textposition='auto',
                marker=dict(
                    color=cluster_sizes,
                    colorscale='Viridis',
                    showscale=True,
                    colorbar=dict(title="Size")
                )
            )
        ])
        
        fig.update_layout(
            title=f'Cluster Sizes<br>{self.cluster.config.chrom}-{self.cluster.config.ctx}',
            xaxis_title='Cluster',
            yaxis_title='Number of Samples',
            width=800,
            height=500
        )
        
        output_file = output_dir / 'cluster_statistics.html'
        fig.write_html(str(output_file))
        logger.info(f"Saved cluster statistics to {output_file}")


__all__ = ['ClusterVisualizer']

