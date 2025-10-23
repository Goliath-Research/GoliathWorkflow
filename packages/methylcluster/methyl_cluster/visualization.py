"""
Visualization module for clustering results.

This module creates comprehensive visualizations of clustering results including
distance matrices, cluster trees, and dimensionality reduction projections.
"""

import numpy as np
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict

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
    
    def _get_label_map(self) -> Dict[int, str]:
        """Get custom label mapping if available."""
        cluster = self.cluster
        label_map = {}
        
        # From forced_groups in config
        if cluster.config.forced_groups is not None:
            labels = list(cluster.config.forced_groups.keys())
            for i, label in enumerate(labels):
                label_map[i] = label
        
        # From internal _group_labels (set during forced init)
        elif hasattr(cluster, '_group_labels') and cluster._group_labels:
            for i, label in enumerate(cluster._group_labels):
                label_map[i] = label
        
        return label_map
    
    def plot_distance_heatmap(self, output_dir: Path) -> None:
        """
        Create distance matrix heatmap with cluster annotations.
        
        Args:
            output_dir: Directory to save plot
        """
        import plotly.graph_objects as go
        import plotly.express as px
        
        logger.info("Creating distance heatmap...")
        
        if self.cluster.distance_matrix is None:
            logger.warning("Distance matrix not available, skipping heatmap")
            return
        
        # Prepare sample names
        sample_names = [str(p.name) for p in self.cluster.sample_paths]
        n_samples = len(sample_names)
        
        # Get custom label map
        label_map = self._get_label_map()
        
        # Create cluster annotations
        annotations = []
        for i in range(n_samples):
            cluster_id = self.cluster.cluster_labels[i]
            if cluster_id == -1:
                label = 'Noise'
            elif cluster_id in label_map:
                label = label_map[cluster_id]
            else:
                label = f'Cluster {cluster_id}'
            annotations.append(label)
        
        # Create the heatmap
        fig = px.imshow(
            self.cluster.distance_matrix,
            labels=dict(x="Sample", y="Sample", color="Distance"),
            x=sample_names,
            y=sample_names,
            title=f'Distance Matrix Heatmap - {self.cluster.config.chrom}-{self.cluster.config.ctx}',
            aspect="auto",
            color_continuous_scale='Viridis'
        )
        
        # Add cluster annotations to hover
        fig.update_traces(
            hovertemplate='<b>Sample X: %{y}</b><br>Sample Y: %{x}<br>Distance: %{z:.4f}<br>Cluster X: ' + 
                          str(annotations) + '[%{y}%<br>Cluster Y: ' + str(annotations) + '[%{x}%<extra></extra>'
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
        
        # Get custom label map for title
        label_map = self._get_label_map()
        custom_title = "HDBSCAN Cluster Tree"
        if label_map:
            group_names = ', '.join(label_map.values())
            custom_title += f' - Groups: {group_names}'
        custom_title += f'\n{self.cluster.config.chrom}-{self.cluster.config.ctx}'
        
        # Create the plot
        plt.figure(figsize=(12, 8))
        
        # Get number of clusters to determine if we should show selection
        unique_labels = set(self.cluster.cluster_labels)
        n_clusters = len(unique_labels - {-1})
        
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
        
        plt.title(custom_title)
        
        output_file = output_dir / 'cluster_tree.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()
        logger.info(f"Saved cluster tree to {output_file}")
    
    def plot_mds_projection(self, output_dir: Path) -> None:
        """
        Create MDS projection plot with custom cluster labels.
        
        Args:
            output_dir: Directory to save plot
        """
        import plotly.graph_objects as go
        import plotly.express as px  # Add this for px.colors
        from sklearn.manifold import MDS
        
        logger.info("Creating MDS projection...")
        
        if self.cluster.distance_matrix is None:
            logger.warning("Distance matrix not available, skipping MDS projection")
            return
        
        # Get custom label map
        label_map = self._get_label_map()
        
        # Perform MDS
        mds = MDS(n_components=2, dissimilarity='precomputed', random_state=42)
        coords = mds.fit_transform(self.cluster.distance_matrix)
        
        # Prepare cluster labels for plotting
        cluster_labels = self.cluster.cluster_labels
        hover_labels = []
        sample_paths = self.cluster.sample_paths
        for i, lbl in enumerate(cluster_labels):
            basename = sample_paths[i].name
            if lbl == -1:
                hover_labels.append(f'<b>{basename}</b>: Noise')
            elif lbl in label_map:
                hover_labels.append(f'<b>{basename}</b>: {label_map[lbl]}')
            else:
                hover_labels.append(f'<b>{basename}</b>: Cluster {lbl}')
        
        # Get unique clusters and colors
        unique_clusters = sorted(set(cluster_labels) - {-1})
        colors = px.colors.qualitative.Set1[:len(unique_clusters)]
        
        # Create traces for each cluster
        fig = go.Figure()
        for idx, cluster_id in enumerate(unique_clusters):
            mask = cluster_labels == cluster_id
            cluster_name = label_map.get(cluster_id, f'Cluster {cluster_id}')
            mask_indices = np.where(mask)[0]
            fig.add_trace(
                go.Scatter(
                    x=coords[mask, 0],
                    y=coords[mask, 1],
                    mode='markers',
                    name=cluster_name,
                    marker=dict(
                        color=colors[idx % len(colors)],
                        size=8,
                        opacity=0.7
                    ),
                    text=[hover_labels[j] for j in mask_indices],
                    hovertemplate='%{text}<extra></extra>'
                )
            )
        
        # Add noise points if any
        noise_mask = cluster_labels == -1
        if np.any(noise_mask):
            noise_indices = np.where(noise_mask)[0]
            fig.add_trace(
                go.Scatter(
                    x=coords[noise_mask, 0],
                    y=coords[noise_mask, 1],
                    mode='markers',
                    name='Noise',
                    marker=dict(
                        color='gray',
                        size=8,
                        opacity=0.5,
                        symbol='x'
                    ),
                    text=[hover_labels[j] for j in noise_indices],
                    hovertemplate='%{text}<extra></extra>'
                )
            )
        
        fig.update_layout(
            title=f'MDS Projection - {self.cluster.config.chrom}-{self.cluster.config.ctx}',
            xaxis_title='MDS Component 1',
            yaxis_title='MDS Component 2',
            legend_title='Clusters',
            hovermode='closest'
        )
        
        output_file = output_dir / 'mds_projection.html'
        fig.write_html(str(output_file))
        logger.info(f"Saved MDS projection to {output_file}")
        if not label_map:
            logger.debug("No custom labels detected for MDS; using numeric cluster IDs")
    
    def plot_cluster_statistics(self, output_dir: Path) -> None:
        """
        Create bar chart of cluster sizes and statistics with custom labels.
        
        Args:
            output_dir: Directory to save plot
        """
        import plotly.graph_objects as go
        
        logger.info("Creating cluster statistics plot...")
        
        # Get custom label map
        label_map = self._get_label_map()
        
        # Count samples per cluster
        unique_labels = sorted(set(self.cluster.cluster_labels))
        cluster_names = []
        cluster_sizes = []
        
        for label in unique_labels:
            count = int(np.sum(self.cluster.cluster_labels == label))
            if label == -1:
                cluster_names.append('Noise')
            elif label in label_map:
                cluster_names.append(label_map[label])
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
            title=f'Cluster Sizes - {self.cluster.config.chrom}-{self.cluster.config.ctx}',
            xaxis_title='Cluster',
            yaxis_title='Number of Samples',
            width=800,
            height=500
        )
        
        output_file = output_dir / 'cluster_statistics.html'
        fig.write_html(str(output_file))
        logger.info(f"Saved cluster statistics to {output_file}")


__all__ = ['ClusterVisualizer']

