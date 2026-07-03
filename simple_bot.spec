# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for MafiaMatrixBot (Windows) — single-file output
#
# Produces: dist/MafiaMatrixBot.exe  (one portable file)
#
# Chrome is NOT bundled — install once with:
#   MafiaMatrixBot.exe --install

from PyInstaller.utils.hooks import collect_data_files, collect_all

patchright_datas, patchright_binaries, patchright_hiddenimports = collect_all('patchright')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=patchright_binaries,
    datas=[
        ('ui/templates',         'ui/templates'),
        ('ui/static',            'ui/static'),
        ('VERSION',              '.'),
    ] + patchright_datas,
    hiddenimports=patchright_hiddenimports + [
        # web framework
        'flask',
        'jinja2',
        'jinja2.ext',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.routing',
        'werkzeug.middleware.shared_data',
        'werkzeug.exceptions',
        # parsing
        'bs4',
        'bs4.builder',
        'bs4.builder._htmlparser',
        'bs4.builder._lxml',
        'lxml',
        'lxml.etree',
        'lxml._elementpath',
        # stdlib extras often missed
        'sqlite3',
        'email.mime.text',
        'email.mime.multipart',
        # project modules
        'action_cooldowns',
        'bot',
        'browser',
        'character_history',
        'config',
        'earn_planner',
        'smart_travel',
        'executor',
        'paths',
        'player_db',
        'players',
        'scheduler',
        'state',
        'sync_client',
        'sync_server',
        'trait_requirements',
        'urls',
        'ui.app',
        # tasks package
        'tasks',
        'tasks.agg_crimes',
        'tasks.away_action',
        'tasks.base',
        'tasks.bionics',
        'tasks.career_training',
        'tasks.case_work',
        'tasks.casino',
        'tasks.character_history',
        'tasks.obituary_history',
        'tasks.smart_travel_task',
        'tasks.check_top_job',
        'tasks.community_service',
        'tasks.consume',
        'tasks.cs_punishment',
        'tasks.deposit',
        'tasks.drug_manufacturing',
        'tasks.drug_trade',
        'tasks.earns',
        'tasks.fire_duties',
        'tasks.gym',
        'tasks.illness',
        'tasks.jail_action',
        'tasks.jail_consume',
        'tasks.jail_duties',
        'tasks.jailbreak',
        'tasks.journal',
        'tasks.login',
        'tasks.maintain_cash',
        'tasks.online_age',
        'tasks.refresh',
        'tasks.snipe_top_job',
        'tasks.withdraw',
        # added modules
        'tasks.auto_jail_time',
        'tasks.auto_promo',
        'tasks.respect',
        'promotions',
        'site_map',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'pandas', 'PIL',
        'IPython', 'jupyter', 'notebook', 'pytest',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

# Single-file EXE — everything bundled in, no COLLECT step
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MafiaMatrixBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=True,
    icon=None,
)
