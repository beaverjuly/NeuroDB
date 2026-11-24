# NeuroDB grading package

Open `results/NeuroDB_Demo.html` to review the executed database queries, three ERD panels, plans, figures, and validation results. The Jupyter notebook in `notebooks/NeuroDB_Demo.ipynb` provides the full teaching walkthrough. The complete 19-table keyed ERD with every attribute is `docs/schema.mmd`. `Launch NeuroDB Explorer.command` opens the live browser interface. Each predefined query shows relevant filters, results, SQL, bound values and its matching diagram. SQL Workspace and `notebooks/SQL_Playground.ipynb` provide a bounded read only route for new questions. Live Experiments runs temporary-table index, selectivity, and materialization comparisons; Benchmark Results retains the separately recorded measurements.

The ZIP includes a MySQL 8.4.11 dump, 378 checksummed public OSF source files, validated timing exports, code, results, and documentation. It excludes local virtual environments and MySQL server files.

To run the live demonstration on macOS, install MySQL 8.4 and Python 3.11, extract the ZIP, and run these commands from the `NeuroDB` folder.

```sh
./scripts/prepare_grader_demo.sh
./'Launch NeuroDB Explorer.command'
```

The setup script imports `database/neurodb.sql` and validates the restored database. Use `Launch NeuroDB.command` for the full Jupyter notebook. MATLAB is needed only to regenerate timing exports from the original MAT files. Set `NEURODB_MYSQL_HOME` if MySQL 8.4 is not installed in `/usr/local/mysql`, or `NEURODB_PYTHON` if Python 3.11 has a different command name.

On Linux with `zsh` available, run the same setup script, then start `.venv/bin/python -m neurodb.webapp` and open `http://127.0.0.1:8765/` in a browser.

On macOS, `Stop NeuroDB.command` stops the local explorer, JupyterLab and MySQL after review.

For the short presentation sequence, see `docs/DEMO_GUIDE.md`. Measurements and interpretation are in `results/RESULTS.md`. The source observations are attributed to the study authors under the OSF CC BY NC SA 4.0 license. Model-derived values cover one validated pilot participant.
