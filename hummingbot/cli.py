#!/usr/bin/env python
"""
Minimalist CLI for Hummingbot using Click.

Usage:
    hummingbot start -f strategy.yml -p password
    hummingbot start -f script.py -c script_config.yml --headless
    HUMMINGBOT_PASSWORD=xxx hummingbot start -f strategy.yml --headless
"""
import asyncio
import logging
import sys
from pathlib import Path

import click

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@click.group()
@click.version_option()
def cli():
    """Hummingbot - Market making and trading bot."""
    pass


@cli.command()
@click.option(
    "-f", "--file",
    "config_file",
    required=True,
    envvar="HUMMINGBOT_CONFIG",
    help="Strategy config (.yml) or script (.py) file.",
)
@click.option(
    "-c", "--script-config",
    envvar="HUMMINGBOT_SCRIPT_CONFIG",
    help="Config file for script strategies.",
)
@click.option(
    "-p", "--password",
    envvar="HUMMINGBOT_PASSWORD",
    hide_input=True,
    prompt=True,
    help="Password to decrypt config files.",
)
@click.option(
    "--headless/--ui",
    default=False,
    envvar="HUMMINGBOT_HEADLESS",
    help="Run without UI (headless mode).",
)
def start(config_file: str, script_config: str, password: str, headless: bool):
    """Start Hummingbot with a strategy."""
    from hummingbot.client.config.config_crypt import ETHKeyFileSecretManger
    from hummingbot.client.config.config_helpers import (
        create_yml_files_legacy,
        load_client_config_map_from_file,
        read_system_configs_from_yml,
    )
    from hummingbot.client.config.security import Security
    from hummingbot.client.hummingbot_application import HummingbotApplication
    from hummingbot.client.settings import AllConnectorSettings

    async def run():
        # Initialize
        client_config_map = load_client_config_map_from_file()
        secrets_manager = ETHKeyFileSecretManger(password)

        if not Security.login(secrets_manager):
            raise click.ClickException("Invalid password.")

        await Security.wait_til_decryption_done()
        await create_yml_files_legacy()

        from hummingbot import init_logging
        init_logging("hummingbot_logs.yml", client_config_map)
        await read_system_configs_from_yml()

        if headless:
            client_config_map.mqtt_bridge.mqtt_autostart = True

        AllConnectorSettings.initialize_paper_trade_settings(
            client_config_map.paper_trade.paper_trade_exchanges
        )

        # Create application
        hb = HummingbotApplication.main_application(
            client_config_map=client_config_map,
            headless_mode=headless
        )

        # Load strategy
        success = await _load_strategy(hb, config_file, script_config, headless)
        if not success:
            raise click.ClickException("Failed to load strategy.")

        # Wait for gateway if needed
        await _wait_for_gateway(hb)

        # Run
        if headless:
            log_file = hb.strategy_file_name.split(".")[0] if hb.strategy_file_name else "hummingbot"
            init_logging(
                "hummingbot_logs.yml",
                hb.client_config_map,
                override_log_level=hb.client_config_map.log_level,
                strategy_file_path=log_file
            )
        await hb.run()

    asyncio.run(run())


async def _load_strategy(hb, config_file: str, script_config: str, headless: bool) -> bool:
    """Load strategy from config file or script."""
    from hummingbot.client.config.config_helpers import (
        ClientConfigAdapter,
        all_configs_complete,
        load_strategy_config_map_from_file,
    )
    from hummingbot.client.settings import (
        SCRIPT_STRATEGIES_PATH,
        SCRIPT_STRATEGY_CONF_DIR_PATH,
        STRATEGIES_CONF_DIR_PATH,
    )

    if config_file.endswith(".py"):
        # Script strategy
        strategy_name = config_file.replace(".py", "")
        script_path = SCRIPT_STRATEGIES_PATH / config_file

        if not script_path.exists():
            logging.error(f"Script not found: {script_path}")
            return False

        if script_config:
            config_path = SCRIPT_STRATEGY_CONF_DIR_PATH / script_config
            if not config_path.exists():
                logging.error(f"Script config not found: {config_path}")
                return False

        hb.strategy_file_name = script_config.split(".")[0] if script_config else strategy_name
        hb.strategy_name = strategy_name

        if headless:
            return await hb.trading_core.start_strategy(
                strategy_name,
                script_config,
                hb.strategy_file_name + (".yml" if script_config else ".py")
            )
        else:
            if script_config:
                hb.script_config = script_config
    else:
        # YAML strategy
        hb.strategy_file_name = config_file.split(".")[0]
        config_path = STRATEGIES_CONF_DIR_PATH / config_file

        try:
            strategy_config = await load_strategy_config_map_from_file(config_path)
        except FileNotFoundError:
            logging.error(f"Config not found: {config_path}")
            return False

        strategy_name = (
            strategy_config.strategy
            if isinstance(strategy_config, ClientConfigAdapter)
            else strategy_config.get("strategy").value
        )
        hb.trading_core.strategy_name = strategy_name

        if headless:
            return await hb.trading_core.start_strategy(
                strategy_name,
                strategy_config,
                config_file
            )
        else:
            hb.strategy_config_map = strategy_config
            if not all_configs_complete(strategy_config, hb.client_config_map):
                hb.status()

    return True


async def _wait_for_gateway(hb):
    """Wait for gateway to be ready if needed."""
    import asyncio

    from hummingbot.client.command.start_command import GATEWAY_READY_TIMEOUT
    from hummingbot.client.settings import AllConnectorSettings

    exchange_settings = [
        AllConnectorSettings.get_connector_settings().get(e, None)
        for e in hb.trading_core.connector_manager.connectors.keys()
    ]
    uses_gateway = any(s.uses_gateway_generic_connector() for s in exchange_settings if s)

    if uses_gateway:
        try:
            await asyncio.wait_for(
                hb.trading_core.gateway_monitor.ready_event.wait(),
                timeout=GATEWAY_READY_TIMEOUT
            )
        except asyncio.TimeoutError:
            raise click.ClickException("Gateway timeout - check gateway configuration.")


@cli.command()
def version():
    """Show version information."""
    from hummingbot import VERSION
    click.echo(f"Hummingbot {VERSION}")


@cli.command()
def config():
    """Show config directory locations."""
    from hummingbot.client.settings import CONF_DIR_PATH, SCRIPT_STRATEGY_CONF_DIR_PATH, STRATEGIES_CONF_DIR_PATH
    click.echo(f"Config:     {CONF_DIR_PATH}")
    click.echo(f"Strategies: {STRATEGIES_CONF_DIR_PATH}")
    click.echo(f"Scripts:    {SCRIPT_STRATEGY_CONF_DIR_PATH}")


def main():
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
