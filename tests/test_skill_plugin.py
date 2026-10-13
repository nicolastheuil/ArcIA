import importlib.util
from pathlib import Path
import unittest
import tempfile
import json
import sys
path=Path(__file__).resolve().parents[1]/'services/skills/plugin.py'
sys.path.insert(0,str(path.parent))
import headroom_file

spec=importlib.util.spec_from_file_location('arcia_skill_plugin',path)
plugin=importlib.util.module_from_spec(spec);spec.loader.exec_module(plugin)


class SkillPluginTests(unittest.TestCase):
    def test_only_qualified_readonly_git_log_is_rewritten(self):
        args={'command':'git log -n 15','cwd':'/synthetic'}
        plugin.rewrite(tool_name='terminal',args=args)
        self.assertEqual(args,{'command':'/opt/arcia-tools/bin/rtk git log -n 15','cwd':'/synthetic'})

    def test_raw_formats_writes_shell_and_other_tools_are_preserved(self):
        for text in ('git log --oneline','git log --format=%H','git --no-pager log','git push','git status','git log; env','git log $(env)','git log | cat','git log -p','git log --output=fixture.txt','git log --max-count=999999','git log main'):
            args={'command':text};plugin.rewrite(tool_name='terminal',args=args)
            self.assertEqual(args['command'],text)
        args={'command':'git log'};plugin.rewrite(tool_name='other',args=args)
        self.assertEqual(args['command'],'git log')

    def test_plugin_registers_native_discovery_hook_and_compression_tool(self):
        class Context:
            def __init__(self):self.sections=[];self.hooks=[];self.tools=[]
            def register_system_prompt_section(self,*args,**kwargs):self.sections.append(args)
            def register_hook(self,*args,**kwargs):self.hooks.append(args)
            def register_tool(self,**kwargs):self.tools.append(kwargs)
        ctx=Context();plugin.register(ctx)
        self.assertIn('catalog_search',ctx.sections[0][1])
        self.assertEqual(ctx.hooks[0][0],'pre_tool_call')
        self.assertEqual(ctx.tools[0]['name'],'arcia_compress_json_file')

    def test_headroom_reads_only_bounded_json_in_personal_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory)/'workspace';workspace.mkdir()
            allowed=workspace/'fixture.json';allowed.write_text('[{"fixture":true}]')
            self.assertEqual(json.loads(headroom_file.read_source('fixture.json',workspace)[1]),[{'fixture':True}])
            private=Path(directory)/'config.yaml';private.write_text('private')
            with self.assertRaises(ValueError):headroom_file.read_source(str(private),workspace)
            allowed.write_text('not json')
            with self.assertRaises(ValueError):headroom_file.read_source('fixture.json',workspace)
