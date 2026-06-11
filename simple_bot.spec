# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('ui/templates', 'ui/templates'),
        ('ui/static',    'ui/static'),
    ],
    hiddenimports=[
        # third-party
        'patchright',
        'patchright.sync_api',
        'flask',
        'jinja2',
        'werkzeug',
        'bs4',
        # project modules
        'bot',
        'browser',
        'character_history',
        'config',
        'executor',
        'paths',
        'players',
        'scheduler',
        'site_map',
        'state',
        'trait_requirements',
        'ui.app',
        # tasks package
        'tasks',
        'tasks.agg_crimes',
        'tasks.away_action',
        'tasks.base',
        'tasks.career_training',
        'tasks.case_work',
        'tasks.character_history',
        'tasks.check_top_job',
        'tasks.community_service',
        'tasks.consume',
        'tasks.deposit',
        'tasks.drug_manufacturing',
        'tasks.earns',
        'tasks.fire_duties',
        'tasks.jail_action',
        'tasks.jail_consume',
        'tasks.jail_duties',
        'tasks.jailbreak',
        'tasks.login',
        'tasks.maintain_cash',
        'tasks.refresh',
        'tasks.snipe_top_job',
        'tasks.withdraw',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MafiaMatrixBot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MafiaMatrixBot',
)
