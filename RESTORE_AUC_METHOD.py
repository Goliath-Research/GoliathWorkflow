#!/usr/bin/env python3
"""
Script to restore the original AUC-based _select_dmps_binary_search method.
This will replace the analytical FPR/FNR method that was breaking accuracy.
"""

original_method = '''    def _select_dmps_binary_search(self, dmp_df: pd.DataFrame) -> pd.DataFrame:
        """
        Select optimal subset of DMPs using binary search to achieve target AUC.
        
        Args:
            dmp_df: DataFrame of filtered DMPs with effect_size computed
            
        Returns:
            DataFrame with top k DMPs selected
        """
        n_dmps = len(dmp_df)
        target_auc = self.config.target_auc
        min_selected = self.config.min_selected_dmps
        
        logger.info(f"🔍 Binary search DMP selection: {n_dmps} candidates, target AUC={target_auc:.3f}")
        
        if n_dmps == 0:
            return dmp_df
        
        # Sort by effect size (descending)
        sorted_df = dmp_df.sort_values('effect_size', ascending=False).reset_index(drop=True)
        
        # Load validation samples once if available (for real AUC computation during binary search)
        self._validation_samples = None
        self._validation_labels = None
        self._validation_dmp_positions = None
        
        if (self.config.validation_mode == "real" and 
            (self.config.centroid1_validation_samples or self.config.centroid2_validation_samples)):
            logger.info("📊 Loading validation samples for binary search...")
            samples_data = self._load_validation_samples_for_binary_search(sorted_df)
            if samples_data is not None:
                self._validation_samples, self._validation_labels, self._validation_dmp_positions = samples_data
                logger.info(f"✅ Loaded {len(self._validation_samples)} validation samples with {len(self._validation_dmp_positions)} positions")
        
        # If min_selected_dmps is specified and we have fewer DMPs, return all
        if min_selected and n_dmps <= min_selected:
            logger.info(f"Only {n_dmps} DMPs available, less than min_selected_dmps={min_selected}, returning all")
            return sorted_df
        
        # Binary search for smallest k that achieves target AUC
        low, high = 1, n_dmps
        best_k = n_dmps  # Default to all DMPs
        
        logger.info(f"Binary search range: {low}-{high}")
        
        while low <= high:
            mid = (low + high) // 2
            test_subset = sorted_df.iloc[:mid]
            performance = self._compute_subset_performance(test_subset, use_gpu=self.config.use_gpu)
            
            logger.info(f"  Testing k={mid}: AUC={performance:.4f}")
            
            if performance >= target_auc:
                # This k achieves target - try smaller k
                best_k = mid
                high = mid - 1
            else:
                # Need larger k
                low = mid + 1
        
        # Apply min_selected_dmps constraint if specified
        if min_selected and best_k < min_selected:
            logger.info(f"Binary search found k={best_k}, but enforcing min_selected_dmps={min_selected}")
            best_k = min(min_selected, n_dmps)
        
        # Apply min_dmps_for_export constraint (ensures enough DMPs for gene mapping)
        min_export = self.config.min_dmps_for_export
        if best_k < min_export:
            logger.info(f"Binary search found k={best_k}, but enforcing min_dmps_for_export={min_export}")
            best_k = min(min_export, n_dmps)
        
        # Verify final performance
        final_subset = sorted_df.iloc[:best_k]
        final_performance = self._compute_subset_performance(final_subset, use_gpu=self.config.use_gpu)
        
        logger.info(f"✅ Binary search complete: selected k={best_k} DMPs with AUC={final_performance:.4f}")
        
        return final_subset
'''

print("Original AUC-based method ready to restore")
print("Lines to replace: 280-410 in trainer_class.py")

