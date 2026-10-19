"""Synthetic wizard UI checks: no server, credentials, or private files."""

import json
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess
import unittest


UI = Path(__file__).resolve().parents[1] / "scripts" / "wizard_ui" / "index.html"


class Elements(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.stack = []
        self.ids = {}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        element = {"tag": tag, "attrs": attrs, "parents": list(self.stack)}
        if "id" in attrs:
            if attrs["id"] in self.ids and (attrs["id"].startswith(("stepContainer", "stepNav", "backup_", "restore_", "git_")) or attrs["id"] == "card_git"):
                raise AssertionError("Duplicate element ID: " + attrs["id"])
            self.ids[attrs["id"]] = element
        if tag not in {"input", "br", "meta", "link", "img", "hr", "source", "wbr"}:
            self.stack.append(element)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                self.stack = self.stack[:index]
                break


class BackupWizardUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = UI.read_text(encoding="utf-8")
        cls.dom = Elements(cls.html)

    def test_five_sibling_steps_and_separate_instance_repo(self):
        pages = [self.dom.ids[f"stepContainer{i}"] for i in range(1, 6)]
        self.assertTrue(all(page["parents"][-1] is pages[0]["parents"][-1] for page in pages))
        self.assertEqual(pages[0]["parents"][-1]["attrs"]["id"], "installSection")
        for i in range(1, 6):
            self.assertEqual(self.dom.ids[f"stepNav{i}"]["attrs"]["onclick"], f"goToStep({i})")
        git_parents = [node["attrs"].get("id") for node in self.dom.ids["card_git"]["parents"]]
        self.assertIn("stepContainer4", git_parents)
        self.assertNotIn("stepContainer3", git_parents)
        deploy_parents = [node["attrs"].get("id") for node in self.dom.ids["deployProgressPanel"]["parents"]]
        self.assertIn("stepContainer5", deploy_parents)

    def test_responsive_fields_status_and_separate_actions(self):
        status = self.dom.ids["backup_status_text"]
        password = self.dom.ids["backup_passphrase_input"]
        self.assertEqual(status["attrs"]["role"], "status")
        self.assertEqual(status["attrs"]["aria-live"], "polite")
        self.assertIn("backup-wide", status["attrs"]["class"])
        self.assertIsNot(status["parents"][-1], password["parents"][-1])
        self.assertIs(status["parents"][-1], password["parents"][-2])
        self.assertIn("repeat(2, minmax(0, 1fr))", self.html)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", self.html)
        action = self.dom.ids["backup_now_button"]
        self.assertIn("backup-actions", action["parents"][-1]["attrs"]["class"])

    def run_js(self, body, functions):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node runtime unavailable for synthetic UI execution")
        matches = list(re.finditer(r"^    (?:async )?function (\w+)\(", self.html, re.MULTILINE))
        pieces = {}
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else self.html.index("  </script>", match.start())
            pieces[match.group(1)] = self.html[match.start():end]
        ids = {key: {"value": el["attrs"].get("value", ""), "checked": False} for key, el in self.dom.ids.items()}
        script = """
const assert = require('node:assert/strict');
const state = {models: [1], infraTarget: 'k8s_existing'};
const elements = IDS;
for (const [id, element] of Object.entries(elements)) {
  const classes = new Set();
  element.classList = {add: (...names) => names.forEach(x => classes.add(x)), remove: (...names) => names.forEach(x => classes.delete(x)), contains: name => classes.has(name), toggle: (name, on) => on ? classes.add(name) : classes.delete(name)};
  element.style = {};
  element.setAttribute = (key, value) => { element[key] = value; };
  element.focus = () => { state.focus = id; };
  element.textContent = '';
}
const document = {
  getElementById: id => elements[id] || null,
  querySelectorAll: selector => Object.entries(elements).filter(([id]) => selector.includes('step-page') ? /^stepContainer/.test(id) : /^stepNav/.test(id)).map(([,el]) => el),
  querySelector: () => null
};
const showToast = () => {};
const selectInfraTarget = () => {};
const updateSummaryView = () => { state.summary = true; };
const switchMainTab = tab => { state.tab = tab; };
const fetchInitialConfig = async () => {};
const fetchBackupInfo = async () => {};
const populateFormWithConfig = () => {};
const collectConfigFromUI = () => ({vmware: {}});
const calls = [];
let apiResponse = {success: false};
const api = async (endpoint, payload) => { calls.push({endpoint, payload}); return apiResponse; };
""".replace("IDS", json.dumps(ids))
        script += "\n".join(pieces[name] for name in functions)
        script += "\n(async () => {\n" + body + "\n})().catch(error => { console.error(error); process.exitCode = 1; });"
        result = subprocess.run([node, "-"], input=script, encoding="utf-8", capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_git_validation_reuse_navigation_and_deployment_payload(self):
        self.run_js("""
goToStep(5);
assert.equal(state.currentStep, 5); // Explicit deferred backup.
elements.git_backup_enabled.checked = true;
goToStep(5);
assert.equal(state.currentStep, 4);
assert.match(elements.gitSetupStatus.textContent, /propriétaire/);
elements.git_provider_select.value = 'gitlab';
elements.git_owner_input.value = 'synthetic/team';
elements.git_repo_input.value = 'instance';
elements.git_token_input.value = 'synthetic-access';
elements.git_passphrase_input.value = 'synthetic-passphrase';
elements.git_passphrase_confirm.value = 'mismatch';
await triggerDeployment(true);
assert.equal(calls.length, 0);
assert.equal(state.focus, 'git_passphrase_confirm');
elements.git_passphrase_confirm.value = 'synthetic-passphrase';
goToStep(5);
assert.equal(state.currentStep, 5);
await triggerDeployment(true);
assert.deepEqual(calls[0].payload.instance_git, {repo_url:'https://gitlab.com/synthetic/team/instance.git', provider:'gitlab', owner:'synthetic/team', repo_name:'instance', token:'synthetic-access', passphrase:'synthetic-passphrase'});
elements.git_token_input.value = '';
elements.git_passphrase_input.value = '';
elements.git_passphrase_confirm.value = '';
state.backupUnlocked = true;
populateInstanceRepo({repo_url:'https://github.com/synthetic/existing.git', token:'NEVER-IN-FORM', passphrase:'NEVER-IN-FORM'});
assert.equal(elements.git_token_input.value, '');
assert.equal(elements.git_passphrase_input.value, '');
assert.equal(validateInstanceGit(), true);
elements.git_backup_enabled.checked = false;
updateGitSetupStatus();
assert.match(elements.gitSetupStatus.textContent, /ne désactive pas/);
elements.git_backup_enabled.checked = true;
elements.git_repo_input.value = 'other';
assert.equal(validateInstanceGit(), false); // Never reuse an unlocked different repo.
exitDeploymentMode();
assert.equal(state.currentStep, 4); // Validation returns to the repo step.
elements.git_backup_enabled.checked = false;
exitDeploymentMode();
assert.equal(state.currentStep, 5);
""", ["getSetupRepoUrl", "setupRepoIsUnlocked", "updateGitSetupStatus", "validateInstanceGit", "populateInstanceRepo", "toggleIntegration", "goToStep", "triggerDeployment", "exitDeploymentMode"])

    def test_restore_prepares_review_and_clears_secret_inputs(self):
        self.run_js("""
for (const id of ['backup_passphrase_input','backup_token_input','restore_git_token','restore_git_passphrase']) elements[id].value = 'synthetic';
await prepareRestoredConfiguration({config: {synthetic: true}, warning: 'PRIVATE-WARNING'});
assert.equal(state.currentStep, 1);
assert.equal(state.tab, 'install');
assert.equal(state.newInstanceFlow, true);
assert.equal(calls.length, 0); // A restore never deploys.
for (const id of ['backup_passphrase_input','backup_token_input','restore_git_token','restore_git_passphrase']) assert.equal(elements[id].value, '');
assert.match(elements.restore_status_text.textContent, /localement/);
assert.match(elements.restore_status_text.textContent, /explicitement/);
assert.match(elements.restorePreparationNotice.textContent, /Ancienne sauvegarde/);
assert.equal(elements.restorePreparationNotice.classList.contains('hidden'), false);
assert.ok(!elements.restorePreparationNotice.textContent.includes('PRIVATE-WARNING'));
""", ["prepareRestoredConfiguration", "goToStep", "validateInstanceGit", "getSetupRepoUrl", "setupRepoIsUnlocked", "updateGitSetupStatus"])

    def test_restore_reuses_only_the_same_unlocked_repo(self):
        self.run_js("""
state.backupUnlocked = true;
state.backupRepoUrl = 'https://github.com/synthetic/instance.git';
elements.restore_git_url.value = 'https://github.com/synthetic/other.git';
await restoreFromGit();
assert.equal(calls.length, 0);
elements.restore_git_url.value = state.backupRepoUrl;
apiResponse = {success: true, config: {synthetic: true}};
await restoreFromGit();
assert.deepEqual(calls[0], {endpoint:'instance/restore', payload:{repo_url:state.backupRepoUrl, token:'', passphrase:''}});
assert.equal(state.currentStep, 1);
assert.equal(state.tab, 'install');
assert.equal(elements.restore_git_button.disabled, false);
""", ["restoreFromGit", "prepareRestoredConfiguration", "goToStep", "validateInstanceGit", "getSetupRepoUrl", "setupRepoIsUnlocked", "updateGitSetupStatus"])

    def test_backup_requests_contract_and_pending_status(self):
        self.run_js("""
elements.backup_repo_input.value = 'https://github.com/synthetic/instance.git';
elements.backup_token_input.value = 'synthetic-access';
elements.backup_passphrase_input.value = 'synthetic-passphrase';
apiResponse = {success: false, state: 'pending', error: 'PRIVATE-ERROR'};
await backupCurrentInstanceNow();
assert.deepEqual(calls[0], {endpoint:'instance/backup-now', payload:{repo_url:'https://github.com/synthetic/instance.git', token:'synthetic-access', passphrase:'synthetic-passphrase'}});
assert.match(elements.backup_status_text.textContent, /en attente/);
assert.ok(!elements.backup_status_text.textContent.includes('PRIVATE-ERROR'));
assert.equal(elements.backup_now_button.disabled, false);
apiResponse = {success:true, state:'pushed'};
await backupCurrentInstanceNow();
assert.equal(elements.backup_token_input.value, '');
assert.equal(elements.backup_passphrase_input.value, '');
assert.match(elements.backup_status_text.textContent, /envoyée/);
""", ["backupCurrentInstanceNow", "backupStatusMessage"])

    def test_backup_coverage_never_renders_paths_or_raw_errors(self):
        self.run_js("""
const text = backupCoverageMessage({managed_files: ['private/path'], referenced_files: 2, total_bytes: 80, missing_references: ['private/path']});
assert.match(text, /1 fichiers gérés/);
assert.match(text, /1 référence/);
assert.ok(!text.includes('private/path'));
const error = backupStatusMessage({state:'pending', error:'PRIVATE-ERROR'}, true);
assert.ok(!error.includes('PRIVATE-ERROR'));
assert.match(error, /en attente/);
assert.match(backupStatusMessage({state:'locked', error:'PRIVATE-ERROR'}, false), /verrouillé/);
assert.match(backupStatusMessage({state:'incomplete', error:'PRIVATE-ERROR'}, true), /refusée/);
assert.match(backupStatusMessage({state:'restored'}, true), /explicitement/);
""", ["backupCoverageMessage", "backupStatusMessage"])


if __name__ == "__main__":
    unittest.main()
