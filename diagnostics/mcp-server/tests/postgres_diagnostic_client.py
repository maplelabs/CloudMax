#!/usr/bin/env python3
"""PostgreSQL Diagnostic MCP Client.

This client connects to the Diagnostic MCP Server and calls
PostgreSQL diagnostic tools.

Usage:
    python3 postgres_diagnostic_client.py [command] [options]

Commands:
    check-access          Check if PostgreSQL database is reachable
    check-locks           Check for pending write locks
    check-connections     Check current vs max connections
    all                   Run all core PostgreSQL checks

Examples:
    python3 postgres_diagnostic_client.py check-access
    python3 postgres_diagnostic_client.py check-locks
    python3 postgres_diagnostic_client.py all
"""

import argparse
import asyncio
import json
import sys

import httpx
from langchain_mcp_adapters.client import MultiServerMCPClient


def create_httpx_client(**kwargs) -> httpx.AsyncClient:
    """Create httpx client for HTTP connections."""
    return httpx.AsyncClient(verify=False)


async def get_mcp_tools(server_url: str = "http://localhost:8080/mcp"):
    """Connect to MCP server and get tools."""
    client = MultiServerMCPClient({
        'diagnostic-server': {
            'url': server_url,
            'transport': 'streamable_http',
            'httpx_client_factory': create_httpx_client,
        }
    })
    tools = await client.get_tools()
    return {t.name: t for t in tools}


def print_result(title: str, result: dict):
    """Pretty print a tool result."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)
    print(json.dumps(result, indent=2))


async def check_access(tools: dict, database_url: Optional[str] = None):
    """Check if PostgreSQL database is reachable."""
    params = {}
    if database_url:
        params['database_url'] = database_url
    
    result = await tools['db_check_access_tool'].ainvoke(params)
    result_data = json.loads(result) if isinstance(result, str) else result
    
    print_result("DATABASE ACCESS CHECK", result_data)
    
    if result_data.get('db_accessible'):
        print("\n✅ Database is ACCESSIBLE")
    else:
        print(f"\n❌ Database is NOT ACCESSIBLE")
        if result_data.get('error'):
            print(f"   Error: {result_data['error']}")
    
    return result_data


async def check_locks(tools: dict):
    """Check for pending write locks."""
    result = await tools['db_check_write_locks_tool'].ainvoke({})
    result_data = json.loads(result) if isinstance(result, str) else result
    
    print_result("WRITE LOCKS CHECK", result_data)
    
    if result_data.get('error'):
        print(f"\n❌ Error: {result_data['error']}")
    elif result_data.get('has_pending_locks'):
        print(f"\n⚠️  {result_data['pending_lock_count']} PENDING WRITE LOCK(S) detected!")
        if result_data.get('locks'):
            for lock in result_data['locks']:
                print(f"   - PID {lock['pid']}: {lock['lock_mode']} on {lock.get('table_name', 'N/A')}")
    else:
        print("\n✅ No pending write locks")
    
    return result_data


async def check_connections(tools: dict):
    """Check current vs max connections."""
    result = await tools['db_check_max_connections_tool'].ainvoke({})
    result_data = json.loads(result) if isinstance(result, str) else result
    
    print_result("MAX CONNECTIONS CHECK", result_data)
    
    if result_data.get('error'):
        print(f"\n❌ Error: {result_data['error']}")
    else:
        current = result_data.get('connection_count', 0)
        max_conn = result_data.get('max_connection_limit', 0)
        usage = result_data.get('usage_percentage', 0)
        
        print(f"\n📊 Connections: {current}/{max_conn} ({usage}%)")
        
        if result_data.get('max_connections_reached'):
            print("⚠️  WARNING: Connection limit reached or near saturation!")
        else:
            print("✅ Connection usage is healthy")
    
    return result_data


async def run_all_checks(tools: dict):
    """Run all diagnostic checks."""
    print("\n" + "="*60)
    print(" RUNNING ALL PostgreSQL DIAGNOSTIC CHECKS")
    print("="*60)

    await check_access(tools)
    await check_locks(tools)
    await check_connections(tools)

    print("\n" + "="*60)
    print(" ALL CHECKS COMPLETED")
    print("="*60 + "\n")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PostgreSQL Diagnostic MCP Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 postgres_diagnostic_client.py check-access
  python3 postgres_diagnostic_client.py check-locks
  python3 postgres_diagnostic_client.py check-connections
  python3 postgres_diagnostic_client.py all
        """
    )

    parser.add_argument(
        'command',
        choices=['check-access', 'check-locks', 'check-connections', 'all'],
        help='Diagnostic command to run'
    )
    parser.add_argument(
        '--server-url',
        default='http://localhost:8080/mcp',
        help='MCP server URL (default: http://localhost:8080/mcp)'
    )
    parser.add_argument(
        '--database-url',
        help='Optional PostgreSQL connection URL for check-access'
    )

    args = parser.parse_args()

    print("="*60)
    print(" PostgreSQL Diagnostic MCP Client")
    print("="*60)
    print(f"Server: {args.server_url}")
    print(f"Command: {args.command}")

    try:
        # Connect to MCP server
        print("\nConnecting to MCP server...")
        tools = await get_mcp_tools(args.server_url)
        print(f"Connected! Found {len(tools)} tools.")

        # Execute command
        if args.command == 'check-access':
            await check_access(tools, args.database_url)
        elif args.command == 'check-locks':
            await check_locks(tools)
        elif args.command == 'check-connections':
            await check_connections(tools)
        elif args.command == 'all':
            await run_all_checks(tools)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

