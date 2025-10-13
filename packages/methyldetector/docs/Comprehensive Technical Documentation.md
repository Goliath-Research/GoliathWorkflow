[39 tools called]

Based on my comprehensive analysis of the MethylDetector codebase, I'll provide you with a detailed documentation update covering all the requested aspects. Here's the complete analysis:

# MethylDetector: Comprehensive Technical Documentation

## I. Theoretical Foundations

### Core Innovation: Extended Centroid-Based Analysis

MethylDetector represents a paradigm shift in DNA methylation analysis by operating on **distributional representations** rather than point estimates. The system uses **extended centroids** that characterize each genomic position by complete Beta distribution parameters (α, β) plus statistical moments.

#### Mathematical Framework

**Beta Distribution Modeling:**
```math
X \sim \text{Beta}(\alpha, \beta)
```
```math
E[X] = \frac{\alpha}{\alpha + \beta}, \quad \text{Var}(X) = \frac{\alpha\beta}{(\alpha + \beta)^2(\alpha + \beta + 1)}
```

**Maximum Likelihood Estimation:**
```math
L(\alpha,\beta) = \prod_i \frac{x_i^{\alpha-1}(1-x_i)^{\beta-1}}{B(\alpha,\beta)}
```

#### Discrimination Analysis

The system employs multiple complementary metrics to transition from statistical to biological significance:

1. **Distribution Overlap**: Measures shared area between Beta distributions
2. **Jeffreys Divergence**: Symmetric measure of distributional difference  
3. **AUC-Based Discrimination**: Binary classification performance
4. **Log-Likelihood Ratio Moments**: Analytical computation of effect size distributions

#### Minimal DMP Selection Algorithm

Uses **composite ranking scores** with **directional handling**:
```math
w[i] = JD[i] \times |AUC_{signed}[i]|^\gamma
```

Followed by **greedy selection** and **backward pruning** to achieve minimal sufficient DMP sets.

## II. Current Implementation Architecture

### Core Components

#### 1. **MethylDetector Class** (`methyl_detector/core/methyldetector.py`)
- Main pipeline orchestrator implementing the 3-phase workflow:
  - **Phase 1**: Statistical DMP detection via Likelihood Ratio Tests
  - **Phase 2**: Biological DMP filtering and selection  
  - **Phase 3**: Results generation and export

#### 2. **CentroidComparer** (`methyl_detector/core/centroid_comparer.py`)
- GPU-accelerated statistical testing with intelligent method selection:
  - Normal approximation for well-behaved distributions (n ≥ 30)
  - Likelihood Ratio Test for complex distributions
  - Automatic fallback strategies

#### 3. **DMPSelector** (`methyl_detector/core/dmp_selector.py`)
- Advanced optimization algorithms for minimal DMP subset selection
- Current: Greedy approach with backward pruning (O(n²))
- Advanced: Genetic algorithms, simulated annealing, branch-and-bound

#### 4. **Configuration System**
- **Pydantic-based models** for type-safe parameter handling
- **JSON configuration files** for reproducible analyses
- **Flexible modes**: Single comparison vs. multiple chromosome-context combinations

### Key Features

- **GPU Acceleration**: CuPy/CuDF integration for high-performance computing
- **FDR Correction**: Storey's π₀ method with interactive visualization
- **Multiple Export Formats**: CSV, Parquet, HDF5, JSON
- **Binary Optimization**: Snappy-compressed Parquet and Z-standard HDF5
- **Container Integration**: Pre-configured GPU environment

## III. Container Usage and Deployment

### Container Architecture

#### **Primary Container: `epimethyl`**
- **Base**: NVIDIA CUDA 12.8 environment
- **GPU Support**: Full CuPy/CuDF acceleration
- **Volume Mounts**:
  - `/home/ubuntu/MethylDetector` - Main project code
  - `/home/ubuntu/MethylUtils` - Shared utilities library
  - `/home/ubuntu/Work` - High-speed storage workspace
  - `/home/ubuntu/working_dir` - Additional workspace

#### **Container Configuration** (`.devcontainer/devcontainer.json`)
```json
{
  "dockerComposeFile": "/home/ubuntu/Work/cuda/docker-compose.yml",
  "service": "gpu_env",
  "containerName": "epimethyl",
  "mounts": [
    "source=/home/ubuntu/MethylUtils,target=/home/ubuntu/MethylUtils,type=bind,consistency=cached",
    "source=/home/ubuntu/Work,target=/home/ubuntu/Work,type=bind,consistency=cached"
  ]
}
```

#### **GPU Configuration**
- **NVIDIA_VISIBLE_DEVICES**: all
- **CUDA_VISIBLE_DEVICES**: 0  
- **Memory Management**: 16GB shared memory (--shm-size=16g)
- **IPC**: Host (--ipc=host)
- **Threading**: Optimized for multi-core (OMP_NUM_THREADS=8)

### Deployment Scripts

#### **`run_in_container.sh`**
- **Automatic MethylUtils Detection**: Searches multiple locations
- **PYTHONPATH Management**: Ensures correct library loading
- **Environment Consistency**: Reproducible execution across deployments

#### **Usage Patterns**
```bash
# Direct container execution (recommended)
docker exec -w /home/ubuntu/MethylDetector epimethyl ./run_in_container.sh python -m methyl_detector config.json

# With verbose output
docker exec -w /home/ubuntu/MethylDetector epimethyl ./run_in_container.sh python -m methyl_detector config.json --verbose
```

## IV. GPU Performance and NVIDIA GH200 Support

### GPU Acceleration Implementation

#### **Hardware Optimization**
- **NVIDIA GH200 Grace Hopper**: 96GB HBM3e memory
- **CUDA 12.8**: Latest driver and runtime support
- **CuPy Integration**: GPU-accelerated numerical computations

#### **Performance Optimizations**

1. **Vectorized Operations**: Batch processing of Beta distribution calculations
2. **Memory Management**: Efficient GPU memory allocation and cleanup
3. **Fallback Strategies**: Seamless CPU/GPU switching based on availability

#### **Key GPU-Accelerated Functions**
- **Beta Distribution Parameters**: MLE estimation on GPU
- **Likelihood Ratio Tests**: Parallel computation across positions
- **Discrimination Metrics**: AUC calculation, divergence measures
- **Large-Scale Filtering**: DMP selection optimization

### Performance Gains

#### **Scalability Improvements**
- **10×-100× speedup** for large datasets (10K-100K DMPs)
- **Linear scaling** with problem size for GPU-bound operations
- **Memory Efficient**: 96GB GH200 capacity handles massive genomic datasets

#### **Real-World Performance**
- **1K DMPs**: ~2-5 seconds
- **10K DMPs**: ~30-60 seconds  
- **50K DMPs**: ~5-10 minutes (divide-and-conquer)
- **100K+ DMPs**: Streaming algorithms maintain reasonable performance

## V. Shared High-Speed Storage Integration

### Storage Architecture

#### **Work Directory Structure**
```
Work/
├── cuda/                    # Container orchestration
├── output_workflows/        # Analysis results
│   └── arabidopsis/
│       ├── detection/       # DMP detection outputs
│       └── centroids/       # Input centroid data
├── MethylUtils/            # Shared utilities
└── working_dir/            # Temporary workspace
```

#### **Volume Mount Configuration**
- **Type**: Bind mounts with cached consistency
- **Access**: Direct filesystem access from container
- **Performance**: High-speed NVMe storage optimized for I/O-intensive workloads

### Data Management

#### **Input Data Organization**
- **Centroid Files**: HDF5 format with Beta distribution parameters
- **Naming Convention**: `{chromosome}-{context}.h5` (e.g., `1-CG.h5`)
- **Directory Structure**: Organized by experimental conditions

#### **Output Optimization**
- **Binary Formats**: Parquet (Snappy) and HDF5 (Z-standard) compression
- **Efficient Storage**: 50-80% size reduction vs. CSV
- **Fast Access**: Column-oriented storage for analytical queries

## VI. Hatchet Dynamic Clients and Lambda Platform Integration

### Current State
**Note**: Hatchet integration is not currently implemented in the codebase. The system is designed for containerized execution but lacks workflow orchestration layer.

### Recommended Implementation Strategy

#### **Hatchet Integration Architecture**
```
Hatchet Workflow Engine
├── Dynamic Clients → Containerized MethylDetector Tasks
├── Lambda Platform → HPC Resource Management
└── Task Orchestration → Distributed Execution
```

#### **Implementation Roadmap**

1. **Phase 1: Container API Wrapper**
   ```python
   # hatchet_client.py
   class MethylDetectorHatchetClient:
       def run_analysis(self, config: MethylDetectorConfig) -> TaskResult:
           """Execute MethylDetector analysis via Hatchet"""
   ```

2. **Phase 2: Lambda Platform Integration**
   - **Resource Allocation**: GPU node provisioning
   - **Task Distribution**: Parallel chromosome-context processing
   - **Result Aggregation**: Centralized output collection

3. **Phase 3: Workflow Orchestration**
   - **Pipeline Definition**: YAML-based workflow specifications
   - **Dependency Management**: Task execution ordering
   - **Error Handling**: Retry logic and failure recovery

#### **Benefits for HPC Deployment**
- **Dynamic Scaling**: On-demand GPU resource allocation
- **Fault Tolerance**: Automatic task retry and recovery
- **Monitoring**: Real-time execution tracking
- **Cost Optimization**: Efficient resource utilization

## VII. Performance Optimization Strategies

### Large-Scale Algorithm Selection

| DMP Count | Algorithm | Time Complexity | Expected Time | Quality |
|-----------|-----------|----------------|---------------|---------|
| < 50 | Simulated Annealing | O(iter × n) | < 10s | 95% |
| 50-1K | Hierarchical Clustering | O(n² + k log k) | < 30s | 90% |
| 1K-5K | Fast Greedy+ | O(k log n) | < 60s | 85% |
| 5K-50K | Divide-and-Conquer | O(n log(n/k)) | < 300s | 80% |
| 50K+ | Streaming + Sampling | O(n) | < 600s | 75% |

### Container Performance Tuning

#### **GPU Memory Optimization**
```bash
# Container startup parameters
--gpus=all \
--ipc=host \
--ulimit=memlock=-1:-1 \
--ulimit=stack=67108864:67108864 \
--shm-size=16g
```

#### **Threading Configuration**
```bash
# Environment variables
OMP_NUM_THREADS=8
MKL_NUM_THREADS=8  
NUMEXPR_NUM_THREADS=8
```

## VIII. Future Enhancements

### Methodological Extensions
1. **Spatial Correlation**: Account for neighboring CpG dependencies
2. **Multi-Context Integration**: Combine CG, CHG, CHH contexts
3. **Time-Series Analysis**: Temporal methylation dynamics

### Algorithmic Improvements  
1. **Adaptive Thresholds**: Data-driven parameter selection
2. **Multi-Objective Optimization**: Balance multiple criteria
3. **Deep Learning Integration**: Neural network-based feature selection

### Infrastructure Enhancements
1. **Hatchet Workflow Integration**: Dynamic task orchestration
2. **Lambda Platform Deployment**: HPC-ready containerization
3. **Monitoring and Profiling**: Performance tracking and optimization

## IX. Conclusion

MethylDetector represents a sophisticated approach to DNA methylation analysis that combines:
- **Theoretical Rigor**: Distributional modeling with advanced statistical methods
- **Computational Efficiency**: GPU acceleration with scalable algorithms  
- **Infrastructure Readiness**: Containerized deployment with storage integration
- **Future-Proofing**: Architecture designed for workflow orchestration and HPC deployment

The system successfully transitions from statistical significance to biological relevance while maintaining practical usability for large-scale genomic research. The containerized architecture and GPU optimization provide the foundation for Hatchet-based workflow integration on Lambda platforms or similar HPC environments.

**Recommended Next Steps:**
1. Implement Hatchet client wrapper for task orchestration
2. Deploy on Lambda platform for production workflows
3. Integrate advanced optimization algorithms for larger datasets
4. Add performance monitoring and profiling capabilities

This comprehensive framework positions MethylDetector as a production-ready tool for modern epigenomic research with clear pathways for scaling to HPC environments.