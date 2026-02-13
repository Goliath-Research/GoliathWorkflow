# Sample names in project config

When **`samples_base_path`** is set (in the project or in a group), each group’s **`sample_paths`** can point to files that list only **sample folder names** (one per line or one column). Each name is resolved to `samples_base_path / name`.

- **Project-level:** Set `"samples_base_path": "/path/to/samples/root"` in the project JSON.
- **Group-level:** Set `"samples_base_path"` on a group to override for that group only.
- **File format:** Use a text file (one name per line) or a CSV whose first column is the sample name. If the first row is a header (`sample`, `path`, `name`, etc.), it is skipped.
- Paths in the file that look absolute (start with `/` or contain `/` or `\`) are left unchanged.

Example: **`configs/project_PCa7_4levels_vs_Healthy_example.json`** uses `samples_base_path` and references `configs/pca1.csv` … `configs/pca4.csv` (each CSV has a `sample` column with folder names). Create **`configs/healthy.csv`** with one column of healthy sample folder names for that example to run.
