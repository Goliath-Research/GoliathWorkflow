#!/usr/bin/env python3
"""
Quick test script to verify the new enrichment functionality
"""

import sys
import os
sys.path.insert(0, '/home/ubuntu/MethylPipeline/packages/methylmapper')

from methyl_mapper.gene_disease_enricher import GeneDiseaseEnricher

def test_enricher_sources():
    """Test different source configurations"""
    print("Testing GeneDiseaseEnricher with different source configurations...")

    # Test 1: Only Grok
    print("\n1. Testing Grok-only enrichment:")
    enricher_grok = GeneDiseaseEnricher(
        grok_api_key="dummy_key",  # Won't actually call API
        disgenet_api_key=None,
        use_grok=True,
        use_disgenet=False
    )
    print(f"   use_grok: {enricher_grok.use_grok}")
    print(f"   use_disgenet: {enricher_grok.use_disgenet}")
    print(f"   grok_api_key available: {enricher_grok.grok_api_key is not None}")
    print(f"   disgenet_api_key available: {enricher_grok.disgenet_api_key is not None}")

    # Test 2: Only DisGeNET
    print("\n2. Testing DisGeNET-only enrichment:")
    enricher_disgenet = GeneDiseaseEnricher(
        grok_api_key=None,
        disgenet_api_key="dummy_key",  # Won't actually call API
        use_grok=False,
        use_disgenet=True
    )
    print(f"   use_grok: {enricher_disgenet.use_grok}")
    print(f"   use_disgenet: {enricher_disgenet.use_disgenet}")
    print(f"   grok_api_key available: {enricher_disgenet.grok_api_key is not None}")
    print(f"   disgenet_api_key available: {enricher_disgenet.disgenet_api_key is not None}")

    # Test 3: Both sources
    print("\n3. Testing both sources enrichment:")
    enricher_both = GeneDiseaseEnricher(
        grok_api_key="dummy_key",
        disgenet_api_key="dummy_key",
        use_grok=True,
        use_disgenet=True
    )
    print(f"   use_grok: {enricher_both.use_grok}")
    print(f"   use_disgenet: {enricher_both.use_disgenet}")
    print(f"   grok_api_key available: {enricher_both.grok_api_key is not None}")
    print(f"   disgenet_api_key available: {enricher_both.disgenet_api_key is not None}")

    print("\n✅ All enricher configurations initialized successfully!")

if __name__ == "__main__":
    test_enricher_sources()
