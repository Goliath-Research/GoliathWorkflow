# ROCm Mojo Giraffe gates (operator checklist)

See methylGrapher-mojo [`docs/ROCM_GIRAFFE_GATES.md`](../../../methylGrapher-mojo/docs/ROCM_GIRAFFE_GATES.md) for image build and host prereqs.

| Gate | Status |
|------|--------|
| `:1.70-mojo-rocm` image build script | In tree (`METHYLGRAPHER_MOJO_GPU_VARIANT=rocm`) |
| `align_device=auto` → AMD when `rocm-smi` present | Device select in `giraffe_device.mojo` |
| Toy GAF parity on MI300-class | Operator measure |
| Buffy wall ≤2 h on AMD | Operator measure |
| DS20M `graph.methyl` vs NVIDIA Mojo | Operator measure |
