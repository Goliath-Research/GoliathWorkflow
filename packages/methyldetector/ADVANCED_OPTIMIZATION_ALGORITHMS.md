# Advanced Optimization Algorithms for Minimal DMP Selection

## Current Implementation Analysis

### 🔍 **Current Greedy Approach**

The existing `select_min_subset_analytic()` function uses:

1. **Forward Greedy Selection**: 
   - Add DMPs in order of ranking (sorted by composite weight)
   - Stop when target performance reached
   
2. **Backward Pruning**:
   - Try removing each selected DMP
   - Keep removal if performance still meets target

**Time Complexity**: O(n²) for backward pruning
**Space Complexity**: O(n)
**Optimality**: No guarantee of global optimum

### ❌ **Limitations of Current Approach**

1. **Greedy Suboptimality**: May get stuck in local optima
2. **Order Dependence**: Results depend on initial sorting
3. **No Look-ahead**: Doesn't consider future interactions
4. **Limited Exploration**: Only tries single additions/removals
5. **No Multi-objective Optimization**: Single metric focus

---

## 🚀 **Advanced Optimization Algorithms**

### 1. **Integer Programming (IP) - Optimal Solution**

#### **Mathematical Formulation**

```math
\text{minimize} \quad \sum_{i=1}^n x_i
```

```math
\text{subject to} \quad f(\{i : x_i = 1\}) \geq \text{target\_performance}
```

```math
x_i \in \{0, 1\} \quad \forall i \in \{1, ..., n\}
```

Where `f(S)` is the performance function (AUC/Youden) for subset S.

#### **Implementation Strategy**

```python
def select_optimal_subset_ip(
    filtered_results: List[DMPFilterResult],
    target_auc: float = 0.95,
    solver: str = 'gurobi',
    time_limit: int = 300
) -> Dict[str, Any]:
    """
    Optimal DMP selection using Integer Programming.
    
    Guarantees global optimum but may be computationally expensive.
    """
    from pulp import LpMinimize, LpProblem, LpVariable, LpBinary, lpSum
    
    n = len(filtered_results)
    
    # Decision variables
    x = [LpVariable(f"x_{i}", cat=LpBinary) for i in range(n)]
    
    # Problem formulation
    prob = LpProblem("Minimal_DMP_Selection", LpMinimize)
    
    # Objective: minimize number of selected DMPs
    prob += lpSum(x)
    
    # Constraint: performance must meet target
    # This requires linearizing the performance function
    prob += performance_constraint(x, filtered_results, target_auc)
    
    # Solve
    prob.solve(solver=solver, timeLimit=time_limit)
    
    # Extract solution
    selected = [i for i in range(n) if x[i].value() == 1]
    
    return {
        "selected_local_idxs": selected,
        "k": len(selected),
        "optimal": True,
        "solver_status": prob.status
    }
```

**Advantages**: Globally optimal, handles complex constraints
**Disadvantages**: Computationally expensive for large n, requires constraint linearization

### 2. **Genetic Algorithm (GA) - Population-based Search**

#### **Algorithm Design**

```python
def select_subset_genetic_algorithm(
    filtered_results: List[DMPFilterResult],
    target_auc: float = 0.95,
    population_size: int = 100,
    generations: int = 200,
    mutation_rate: float = 0.01,
    crossover_rate: float = 0.8
) -> Dict[str, Any]:
    """
    DMP selection using Genetic Algorithm.
    
    Explores multiple solutions simultaneously with evolutionary operators.
    """
    
    class DMPChromosome:
        def __init__(self, genes: np.ndarray):
            self.genes = genes  # Binary array [0,1]^n
            self.fitness = None
            self.performance = None
            
        def evaluate(self):
            selected_dmps = [i for i, gene in enumerate(self.genes) if gene == 1]
            if len(selected_dmps) == 0:
                self.fitness = float('inf')
                self.performance = 0.0
                return
                
            # Compute performance using analytical method
            performance = compute_subset_performance(selected_dmps, filtered_results)
            
            if performance >= target_auc:
                self.fitness = len(selected_dmps)  # Minimize size
            else:
                # Penalty for not meeting target
                self.fitness = len(selected_dmps) + 1000 * (target_auc - performance)
            
            self.performance = performance
    
    def crossover(parent1: DMPChromosome, parent2: DMPChromosome) -> Tuple[DMPChromosome, DMPChromosome]:
        """Two-point crossover with repair mechanism."""
        n = len(parent1.genes)
        point1, point2 = sorted(np.random.choice(n, 2, replace=False))
        
        child1_genes = parent1.genes.copy()
        child2_genes = parent2.genes.copy()
        
        child1_genes[point1:point2] = parent2.genes[point1:point2]
        child2_genes[point1:point2] = parent1.genes[point1:point2]
        
        return DMPChromosome(child1_genes), DMPChromosome(child2_genes)
    
    def mutate(chromosome: DMPChromosome) -> DMPChromosome:
        """Bit-flip mutation with adaptive rates."""
        genes = chromosome.genes.copy()
        for i in range(len(genes)):
            if np.random.random() < mutation_rate:
                genes[i] = 1 - genes[i]  # Flip bit
        return DMPChromosome(genes)
    
    # Initialize population
    n = len(filtered_results)
    population = []
    
    # Seed with greedy solution
    greedy_result = select_min_subset_analytic(filtered_results, target_auc)
    greedy_genes = np.zeros(n, dtype=int)
    greedy_genes[greedy_result["selected_local_idxs"]] = 1
    population.append(DMPChromosome(greedy_genes))
    
    # Random initialization for rest
    for _ in range(population_size - 1):
        genes = np.random.choice([0, 1], size=n, p=[0.8, 0.2])  # Sparse initialization
        population.append(DMPChromosome(genes))
    
    # Evolution loop
    best_solution = None
    best_fitness = float('inf')
    
    for generation in range(generations):
        # Evaluate population
        for individual in population:
            individual.evaluate()
            if individual.fitness < best_fitness:
                best_fitness = individual.fitness
                best_solution = individual
        
        # Selection (tournament)
        new_population = []
        for _ in range(population_size):
            tournament = np.random.choice(population, 3)
            winner = min(tournament, key=lambda x: x.fitness)
            new_population.append(winner)
        
        # Crossover and mutation
        next_population = []
        for i in range(0, population_size, 2):
            parent1, parent2 = new_population[i], new_population[i+1 if i+1 < population_size else 0]
            
            if np.random.random() < crossover_rate:
                child1, child2 = crossover(parent1, parent2)
            else:
                child1, child2 = parent1, parent2
            
            next_population.extend([mutate(child1), mutate(child2)])
        
        population = next_population[:population_size]
    
    # Return best solution
    selected = [i for i, gene in enumerate(best_solution.genes) if gene == 1]
    
    return {
        "selected_local_idxs": selected,
        "k": len(selected),
        "final_performance": best_solution.performance,
        "generations": generations,
        "algorithm": "genetic_algorithm"
    }
```

**Advantages**: Explores diverse solutions, handles non-linear objectives, parallelizable
**Disadvantages**: No optimality guarantee, requires parameter tuning

### 3. **Simulated Annealing (SA) - Probabilistic Local Search**

#### **Implementation**

```python
def select_subset_simulated_annealing(
    filtered_results: List[DMPFilterResult],
    target_auc: float = 0.95,
    initial_temp: float = 100.0,
    final_temp: float = 0.1,
    cooling_rate: float = 0.95,
    max_iterations: int = 10000
) -> Dict[str, Any]:
    """
    DMP selection using Simulated Annealing.
    
    Probabilistically escapes local optima with temperature-controlled acceptance.
    """
    
    def objective_function(selected_indices: List[int]) -> float:
        """Objective to minimize: penalized subset size."""
        if len(selected_indices) == 0:
            return float('inf')
        
        performance = compute_subset_performance(selected_indices, filtered_results)
        
        if performance >= target_auc:
            return len(selected_indices)  # Minimize size if feasible
        else:
            # Heavy penalty for infeasible solutions
            return len(selected_indices) + 1000 * (target_auc - performance) ** 2
    
    def get_neighbors(current_solution: List[int], n_total: int) -> List[List[int]]:
        """Generate neighbor solutions by add/remove/swap operations."""
        neighbors = []
        current_set = set(current_solution)
        
        # Add operation: add one DMP not in current solution
        for i in range(n_total):
            if i not in current_set:
                neighbors.append(sorted(current_solution + [i]))
        
        # Remove operation: remove one DMP from current solution
        if len(current_solution) > 1:
            for i in current_solution:
                new_solution = [j for j in current_solution if j != i]
                neighbors.append(new_solution)
        
        # Swap operation: replace one DMP with another
        for i in current_solution:
            for j in range(n_total):
                if j not in current_set:
                    new_solution = [k if k != i else j for k in current_solution]
                    neighbors.append(sorted(new_solution))
        
        return neighbors
    
    # Initialize with greedy solution
    greedy_result = select_min_subset_analytic(filtered_results, target_auc)
    current_solution = greedy_result["selected_local_idxs"]
    current_cost = objective_function(current_solution)
    
    best_solution = current_solution.copy()
    best_cost = current_cost
    
    temperature = initial_temp
    n_total = len(filtered_results)
    
    for iteration in range(max_iterations):
        # Generate random neighbor
        neighbors = get_neighbors(current_solution, n_total)
        if not neighbors:
            break
            
        neighbor = np.random.choice(len(neighbors))
        new_solution = neighbors[neighbor]
        new_cost = objective_function(new_solution)
        
        # Acceptance criterion
        if new_cost < current_cost:
            # Accept improvement
            current_solution = new_solution
            current_cost = new_cost
            
            if new_cost < best_cost:
                best_solution = new_solution.copy()
                best_cost = new_cost
        else:
            # Accept with probability based on temperature
            delta = new_cost - current_cost
            probability = np.exp(-delta / temperature)
            
            if np.random.random() < probability:
                current_solution = new_solution
                current_cost = new_cost
        
        # Cool down
        temperature *= cooling_rate
        if temperature < final_temp:
            break
    
    return {
        "selected_local_idxs": best_solution,
        "k": len(best_solution),
        "final_cost": best_cost,
        "iterations": iteration + 1,
        "algorithm": "simulated_annealing"
    }
```

**Advantages**: Escapes local optima, simple implementation, good for medium-sized problems
**Disadvantages**: Requires parameter tuning, no optimality guarantee

### 4. **Branch and Bound - Exact Algorithm**

#### **Implementation**

```python
def select_subset_branch_and_bound(
    filtered_results: List[DMPFilterResult],
    target_auc: float = 0.95,
    time_limit: int = 300
) -> Dict[str, Any]:
    """
    Exact DMP selection using Branch and Bound.
    
    Guarantees optimal solution with intelligent pruning.
    """
    import heapq
    import time
    
    start_time = time.time()
    n = len(filtered_results)
    
    # Precompute individual contributions for bounds
    individual_contributions = []
    for i, result in enumerate(filtered_results):
        perf = compute_subset_performance([i], filtered_results)
        individual_contributions.append((perf, result.w if hasattr(result, 'w') else 1.0))
    
    # Sort by contribution for better bounds
    sorted_indices = sorted(range(n), key=lambda i: individual_contributions[i][0], reverse=True)
    
    class Node:
        def __init__(self, included: List[int], excluded: List[int], depth: int):
            self.included = included
            self.excluded = excluded
            self.depth = depth
            self.lower_bound = self.compute_lower_bound()
            self.upper_bound = self.compute_upper_bound()
            self.performance = None
            
        def compute_lower_bound(self) -> int:
            """Lower bound: current size (if feasible)."""
            if self.is_feasible():
                return len(self.included)
            else:
                return len(self.included) + 1  # Need at least one more
        
        def compute_upper_bound(self) -> int:
            """Upper bound: greedy estimation."""
            if self.is_feasible():
                return len(self.included)
            
            # Estimate minimum additions needed
            remaining = [i for i in range(n) if i not in self.excluded and i not in self.included]
            if not remaining:
                return float('inf')
            
            # Greedy estimate
            current_perf = self.get_performance()
            needed_perf = target_auc - current_perf
            
            # Estimate based on best remaining contributions
            remaining_contribs = [individual_contributions[i][0] for i in remaining]
            remaining_contribs.sort(reverse=True)
            
            estimated_additions = 0
            estimated_gain = 0.0
            for contrib in remaining_contribs:
                if estimated_gain >= needed_perf:
                    break
                estimated_gain += contrib * 0.8  # Discount for interaction
                estimated_additions += 1
            
            return len(self.included) + estimated_additions
        
        def is_feasible(self) -> bool:
            """Check if current solution meets target performance."""
            if len(self.included) == 0:
                return False
            performance = self.get_performance()
            return performance >= target_auc
        
        def get_performance(self) -> float:
            """Compute performance of current solution."""
            if self.performance is None:
                if len(self.included) == 0:
                    self.performance = 0.0
                else:
                    self.performance = compute_subset_performance(self.included, filtered_results)
            return self.performance
        
        def __lt__(self, other):
            return self.lower_bound < other.lower_bound
    
    # Priority queue for branch and bound
    pq = []
    heapq.heappush(pq, Node([], [], 0))
    
    best_solution = None
    best_size = float('inf')
    nodes_explored = 0
    
    while pq and (time.time() - start_time) < time_limit:
        current = heapq.heappop(pq)
        nodes_explored += 1
        
        # Pruning
        if current.lower_bound >= best_size:
            continue
        
        # Check if complete solution
        if current.depth == n:
            if current.is_feasible() and len(current.included) < best_size:
                best_solution = current.included.copy()
                best_size = len(current.included)
            continue
        
        # Branch: include or exclude next variable
        next_var = sorted_indices[current.depth]
        
        # Branch 1: Include next variable
        new_included = current.included + [next_var]
        new_excluded = current.excluded.copy()
        child1 = Node(new_included, new_excluded, current.depth + 1)
        
        if child1.lower_bound < best_size:
            heapq.heappush(pq, child1)
        
        # Branch 2: Exclude next variable
        new_included = current.included.copy()
        new_excluded = current.excluded + [next_var]
        child2 = Node(new_included, new_excluded, current.depth + 1)
        
        if child2.upper_bound < best_size:
            heapq.heappush(pq, child2)
    
    optimal = (time.time() - start_time) < time_limit and len(pq) == 0
    
    return {
        "selected_local_idxs": best_solution if best_solution else [],
        "k": len(best_solution) if best_solution else 0,
        "optimal": optimal,
        "nodes_explored": nodes_explored,
        "time_elapsed": time.time() - start_time,
        "algorithm": "branch_and_bound"
    }
```

**Advantages**: Guarantees optimal solution, intelligent pruning
**Disadvantages**: Exponential worst-case complexity, may timeout on large instances

### 5. **Multi-Objective Optimization (NSGA-II)**

#### **Implementation for Multiple Objectives**

```python
def select_subset_nsga2(
    filtered_results: List[DMPFilterResult],
    objectives: List[str] = ['size', 'auc', 'diversity'],
    population_size: int = 100,
    generations: int = 200
) -> Dict[str, Any]:
    """
    Multi-objective DMP selection using NSGA-II.
    
    Optimizes multiple objectives simultaneously (e.g., size, performance, diversity).
    """
    
    class MultiObjectiveSolution:
        def __init__(self, genes: np.ndarray):
            self.genes = genes
            self.objectives = {}
            self.rank = None
            self.crowding_distance = 0.0
            
        def evaluate_objectives(self):
            selected = [i for i, gene in enumerate(self.genes) if gene == 1]
            
            if len(selected) == 0:
                self.objectives = {obj: float('inf') for obj in objectives}
                return
            
            # Objective 1: Minimize subset size
            self.objectives['size'] = len(selected)
            
            # Objective 2: Maximize performance (minimize negative performance)
            performance = compute_subset_performance(selected, filtered_results)
            self.objectives['auc'] = -performance  # Minimize negative AUC
            
            # Objective 3: Maximize diversity (minimize negative diversity)
            if 'diversity' in objectives:
                diversity = compute_subset_diversity(selected, filtered_results)
                self.objectives['diversity'] = -diversity
        
        def dominates(self, other) -> bool:
            """Check if this solution dominates another."""
            better_in_any = False
            for obj in objectives:
                if self.objectives[obj] > other.objectives[obj]:
                    return False  # Other is better in this objective
                elif self.objectives[obj] < other.objectives[obj]:
                    better_in_any = True
            return better_in_any
    
    def fast_non_dominated_sort(population: List[MultiObjectiveSolution]) -> List[List[int]]:
        """Classify population into non-dominated fronts."""
        fronts = [[]]
        domination_count = [0] * len(population)
        dominated_solutions = [[] for _ in range(len(population))]
        
        for i, p in enumerate(population):
            for j, q in enumerate(population):
                if p.dominates(q):
                    dominated_solutions[i].append(j)
                elif q.dominates(p):
                    domination_count[i] += 1
            
            if domination_count[i] == 0:
                fronts[0].append(i)
                p.rank = 0
        
        front_idx = 0
        while fronts[front_idx]:
            next_front = []
            for i in fronts[front_idx]:
                for j in dominated_solutions[i]:
                    domination_count[j] -= 1
                    if domination_count[j] == 0:
                        next_front.append(j)
                        population[j].rank = front_idx + 1
            
            if next_front:
                fronts.append(next_front)
            front_idx += 1
        
        return fronts[:-1]  # Remove empty last front
    
    def calculate_crowding_distance(population: List[MultiObjectiveSolution], front: List[int]):
        """Calculate crowding distance for solutions in a front."""
        if len(front) <= 2:
            for i in front:
                population[i].crowding_distance = float('inf')
            return
        
        for i in front:
            population[i].crowding_distance = 0
        
        for obj in objectives:
            # Sort by objective value
            front.sort(key=lambda i: population[i].objectives[obj])
            
            # Boundary points get infinite distance
            population[front[0]].crowding_distance = float('inf')
            population[front[-1]].crowding_distance = float('inf')
            
            # Calculate distance for interior points
            obj_range = (population[front[-1]].objectives[obj] - 
                        population[front[0]].objectives[obj])
            
            if obj_range > 0:
                for i in range(1, len(front) - 1):
                    distance = (population[front[i+1]].objectives[obj] - 
                              population[front[i-1]].objectives[obj]) / obj_range
                    population[front[i]].crowding_distance += distance
    
    # Initialize population
    n = len(filtered_results)
    population = []
    
    for _ in range(population_size):
        genes = np.random.choice([0, 1], size=n, p=[0.8, 0.2])
        solution = MultiObjectiveSolution(genes)
        solution.evaluate_objectives()
        population.append(solution)
    
    # Evolution
    for generation in range(generations):
        # Non-dominated sorting
        fronts = fast_non_dominated_sort(population)
        
        # Calculate crowding distance
        for front in fronts:
            calculate_crowding_distance(population, front)
        
        # Selection for next generation
        new_population = []
        for front in fronts:
            if len(new_population) + len(front) <= population_size:
                new_population.extend([population[i] for i in front])
            else:
                # Sort by crowding distance and take best
                remaining = population_size - len(new_population)
                front.sort(key=lambda i: population[i].crowding_distance, reverse=True)
                new_population.extend([population[i] for i in front[:remaining]])
                break
        
        # Generate offspring (simplified)
        while len(new_population) < population_size * 2:
            parent1, parent2 = np.random.choice(new_population, 2)
            # Crossover and mutation (simplified)
            child_genes = (parent1.genes + parent2.genes) // 2
            child = MultiObjectiveSolution(child_genes)
            child.evaluate_objectives()
            new_population.append(child)
        
        population = new_population[:population_size]
    
    # Return Pareto front solutions
    fronts = fast_non_dominated_sort(population)
    pareto_front = [population[i] for i in fronts[0]]
    
    # Select best compromise solution (e.g., closest to ideal point)
    best_solution = min(pareto_front, key=lambda x: sum(x.objectives.values()))
    selected = [i for i, gene in enumerate(best_solution.genes) if gene == 1]
    
    return {
        "selected_local_idxs": selected,
        "k": len(selected),
        "pareto_front_size": len(pareto_front),
        "objectives": best_solution.objectives,
        "algorithm": "nsga2"
    }
```

**Advantages**: Handles multiple objectives, provides trade-off solutions
**Disadvantages**: Complex implementation, requires objective weighting for final selection

---

## 📊 **Algorithm Comparison Matrix**

| Algorithm | Optimality | Time Complexity | Space | Multi-Objective | Implementation |
|-----------|------------|----------------|-------|-----------------|----------------|
| **Current Greedy** | ❌ Local | O(n²) | O(n) | ❌ | Simple |
| **Integer Programming** | ✅ Global | Exponential | O(n) | ✅ | Complex |
| **Genetic Algorithm** | ❌ Heuristic | O(g×p×n) | O(p×n) | ✅ | Moderate |
| **Simulated Annealing** | ❌ Heuristic | O(i×n) | O(n) | ❌ | Simple |
| **Branch & Bound** | ✅ Global | Exponential | O(2ⁿ) | ❌ | Moderate |
| **NSGA-II** | ❌ Heuristic | O(g×p²×m) | O(p×n) | ✅ | Complex |

Where: n=DMPs, g=generations, p=population, i=iterations, m=objectives

---

## 🎯 **Recommended Implementation Strategy**

### **Phase 1: Hybrid Approach**
```python
def select_optimal_subset_hybrid(
    filtered_results: List[DMPFilterResult],
    target_auc: float = 0.95,
    time_budget: int = 60,
    use_exact: bool = True
) -> Dict[str, Any]:
    """
    Hybrid optimization combining multiple algorithms.
    """
    n = len(filtered_results)
    
    # For small problems (n < 50), use exact methods
    if n < 50 and use_exact:
        try:
            return select_subset_branch_and_bound(
                filtered_results, target_auc, time_budget
            )
        except TimeoutError:
            pass  # Fall back to heuristics
    
    # For medium problems (50 ≤ n < 500), use Simulated Annealing
    if n < 500:
        return select_subset_simulated_annealing(
            filtered_results, target_auc, max_iterations=time_budget*100
        )
    
    # For large problems (n ≥ 500), use Genetic Algorithm
    return select_subset_genetic_algorithm(
        filtered_results, target_auc, 
        population_size=min(100, n//5),
        generations=time_budget//2
    )
```

### **Phase 2: GPU-Accelerated Implementation**
```python
def select_subset_gpu_accelerated(
    filtered_results: List[DMPFilterResult],
    target_auc: float = 0.95,
    algorithm: str = 'genetic'
) -> Dict[str, Any]:
    """
    GPU-accelerated optimization using CuPy.
    """
    if not GPU_AVAILABLE:
        return select_optimal_subset_hybrid(filtered_results, target_auc)
    
    # Move computations to GPU
    # Vectorize performance calculations
    # Parallel population evaluation
    # etc.
```

---

## 🚀 **Implementation Priority**

1. **Immediate (Week 1)**: Implement Simulated Annealing - best balance of quality vs. complexity
2. **Short-term (Week 2-3)**: Add Genetic Algorithm for larger instances
3. **Medium-term (Month 1-2)**: Implement Branch & Bound for small instances
4. **Long-term (Month 3+)**: Multi-objective optimization and GPU acceleration

This approach would significantly improve the quality of DMP selection while maintaining computational feasibility for real-world genomic datasets.
