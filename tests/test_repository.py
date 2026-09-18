from pathlib import Path
import subprocess
import tempfile
import unittest

from orchestrator.repository import aggregate, measure


class RepositoryTest(unittest.TestCase):
    def test_metrics_count_commit_not_worktree_and_skip_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            subprocess.run(["git","init","-q",temp], check=True)
            (path/"app.py").write_text("# café\nprint('a')\n")
            (path/"README.md").write_text("# Fixture\n")
            (path/"node_modules").mkdir(); (path/"node_modules"/"large.js").write_text("excluded\n")
            (path/"binary.dat").write_bytes(b"a\x00b")
            (path/"outside").symlink_to("/etc/passwd")
            subprocess.run(["git","-C",temp,"add","."],check=True)
            subprocess.run(["git","-C",temp,"-c","user.name=Fixture","-c","user.email=fixture@example.invalid","-c","core.hooksPath=/dev/null","commit","-qm","fixture"],check=True)
            (path/"app.py").write_text("uncommitted\n"*20)
            repo={"id":"fixture","path":temp,"ref":"HEAD"}
            result=measure(repo)
            self.assertEqual(result["status"],"measured")
            self.assertEqual(result["lines"],3); self.assertEqual(result["files"],2)
            self.assertEqual(result["groups"]["source"]["lines"],2)
            self.assertEqual(result["characters"],len("# café\nprint('a')\n# Fixture\n"))
            later={**result,"at":result["at"]+1}
            total=aggregate({"repositories":[repo],"workers":[],"metrics":[result,later]})
            self.assertEqual(total["aggregate"]["lines"],3)

    def test_missing_repo_is_unavailable_not_zero(self):
        result=measure({"id":"missing","path":None,"ref":"HEAD"})
        self.assertEqual(result["status"],"unavailable")
        self.assertIsNone(result["tokens"])
        self.assertIsNone(result["lines"])


if __name__ == "__main__": unittest.main()
