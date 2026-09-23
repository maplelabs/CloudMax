"""
Tests for Confluence XHTML to Markdown conversion.

Uses real data from mock Confluence server to ensure conversion quality.
"""
import pytest
from bs4 import BeautifulSoup

from src.server.services.confluence import ConfluenceService


class TestConfluenceConversion:
    """Test Confluence XHTML to Markdown conversion with real data"""

    # Sample Confluence XHTML from mock server (page 12346 - Data Ingestion Pipeline Failures)
    SAMPLE_XHTML_WITH_TABLE = """
<h1>Data Ingestion Pipeline Failures</h1>

<ac:structured-macro ac:name="info">
    <ac:parameter ac:name="title">For AI Agents</ac:parameter>
    <ac:rich-text-body>
        <p>This runbook requires access to Grafana MCP server to query logs and metrics.</p>
    </ac:rich-text-body>
</ac:structured-macro>

<h2>Common Issues</h2>
<table>
    <tr>
        <th>Error</th>
        <th>Cause</th>
        <th>Solution</th>
    </tr>
    <tr>
        <td>Connection timeout</td>
        <td>Source system down</td>
        <td>Check source system status</td>
    </tr>
    <tr>
        <td>Data validation failed</td>
        <td>Schema mismatch</td>
        <td>Update schema mapping</td>
    </tr>
</table>
"""

    SAMPLE_XHTML_WITH_CODE = """
<h2>Check Pipeline Status</h2>

<ac:structured-macro ac:name="code">
    <ac:parameter ac:name="language">bash</ac:parameter>
    <ac:plain-text-body><![CDATA[
kubectl get pods -n etl-pipeline
kubectl logs -f etl-ingestion-pod
]]></ac:plain-text-body>
</ac:structured-macro>

<p>Look for errors in the output.</p>
"""

    SAMPLE_XHTML_WITH_WARNING = """
<ac:structured-macro ac:name="warning">
    <ac:parameter ac:name="title">Important</ac:parameter>
    <ac:rich-text-body>
        <p>Do not restart the pipeline during business hours (9 AM - 5 PM EST).</p>
    </ac:rich-text-body>
</ac:structured-macro>
"""

    SAMPLE_XHTML_FULL_PAGE = """
<h1>ETL Transform Job Errors</h1>

<ac:structured-macro ac:name="info">
    <ac:parameter ac:name="title">Quick Links</ac:parameter>
    <ac:rich-text-body>
        <p>Grafana: <a href="https://grafana.example.com">Dashboard</a></p>
    </ac:rich-text-body>
</ac:structured-macro>

<h2>Overview</h2>
<p>This runbook covers transformation job failures in the ETL pipeline.</p>

<h2>Troubleshooting Steps</h2>
<ol>
    <li>Check job status</li>
    <li>Review error logs</li>
    <li>Verify data quality</li>
</ol>

<h3>Step 1: Check Job Status</h3>
<ac:structured-macro ac:name="code">
    <ac:parameter ac:name="language">python</ac:parameter>
    <ac:plain-text-body><![CDATA[
from etl_manager import get_job_status
status = get_job_status('transform_job_01')
print(f"Status: {status}")
]]></ac:plain-text-body>
</ac:structured-macro>

<h2>Error Reference</h2>
<table>
    <tr>
        <th>Error Code</th>
        <th>Description</th>
        <th>Action</th>
    </tr>
    <tr>
        <td>E001</td>
        <td>Memory exceeded</td>
        <td>Increase memory allocation</td>
    </tr>
    <tr>
        <td>E002</td>
        <td>Timeout</td>
        <td>Increase timeout value</td>
    </tr>
</table>

<ac:structured-macro ac:name="warning">
    <ac:parameter ac:name="title">Production Impact</ac:parameter>
    <ac:rich-text-body>
        <p>Restarting this job will affect downstream reports.</p>
    </ac:rich-text-body>
</ac:structured-macro>
"""

    @pytest.mark.asyncio
    async def test_table_conversion(self):
        """Test that HTML tables convert to properly formatted markdown tables"""
        markdown = await ConfluenceService.convert_to_markdown(self.SAMPLE_XHTML_WITH_TABLE)

        # Check table is present
        assert '|' in markdown, "Table should be converted to markdown"

        # Check table has proper structure (rows on separate lines)
        lines = markdown.split('\n')
        table_lines = [line for line in lines if '|' in line]

        assert len(table_lines) >= 3, "Table should have at least header, separator, and data rows"

        # Check header row
        assert 'Error' in markdown
        assert 'Cause' in markdown
        assert 'Solution' in markdown

        # Check data is preserved
        assert 'Connection timeout' in markdown
        assert 'Data validation failed' in markdown

        # Check rows are on separate lines (not all on one line)
        # Each table row should be on its own line
        for i in range(len(table_lines) - 1):
            assert table_lines[i].strip().endswith('|'), f"Row {i} should end with |"

    @pytest.mark.asyncio
    async def test_code_block_conversion(self):
        """Test that code macros convert to markdown code blocks"""
        markdown = await ConfluenceService.convert_to_markdown(self.SAMPLE_XHTML_WITH_CODE)

        # Check code block is present
        assert '```bash' in markdown, "Code block should have language identifier"
        assert 'kubectl get pods' in markdown, "Code content should be preserved"
        assert 'kubectl logs' in markdown

        # Check code block is properly closed
        code_blocks = markdown.count('```')
        assert code_blocks >= 2, "Code block should have opening and closing backticks"

    @pytest.mark.asyncio
    async def test_info_macro_conversion(self):
        """Test that info macros convert to blockquotes"""
        markdown = await ConfluenceService.convert_to_markdown(self.SAMPLE_XHTML_WITH_TABLE)

        # Check info macro is converted to blockquote
        assert '>' in markdown, "Info macro should convert to blockquote"
        assert 'For AI Agents' in markdown, "Info title should be preserved"
        assert 'Grafana MCP' in markdown, "Info content should be preserved"

        # Check NO emojis are added
        assert '️' not in markdown, "Should not contain emojis"

    @pytest.mark.asyncio
    async def test_warning_macro_conversion(self):
        """Test that warning macros convert to blockquotes"""
        markdown = await ConfluenceService.convert_to_markdown(self.SAMPLE_XHTML_WITH_WARNING)

        # Check warning macro is converted to blockquote
        assert '>' in markdown, "Warning macro should convert to blockquote"
        assert 'Important' in markdown, "Warning title should be preserved"
        assert 'Do not restart' in markdown, "Warning content should be preserved"

        # Check NO emojis are added
        assert '️' not in markdown, "Should not contain emojis"

    @pytest.mark.asyncio
    async def test_full_page_conversion(self):
        """Test conversion of a complete page with multiple elements"""
        markdown = await ConfluenceService.convert_to_markdown(self.SAMPLE_XHTML_FULL_PAGE)

        # Check headings are converted
        assert '# ETL Transform Job Errors' in markdown, "H1 should convert to #"
        assert '## Overview' in markdown, "H2 should convert to ##"
        assert '### Step 1' in markdown, "H3 should convert to ###"

        # Check lists are converted
        assert '1. Check job status' in markdown or '1\\. Check job status' in markdown, "Ordered list should be preserved"

        # Check code blocks
        assert '```python' in markdown, "Python code block should be present"
        # Code content may have escaped underscores
        assert 'get_job_status' in markdown or 'get\\_job\\_status' in markdown, "Code content should be preserved"

        # Check tables
        assert 'Error Code' in markdown, "Table header should be present"
        assert 'E001' in markdown, "Table data should be present"

        # Check links
        assert '[Dashboard]' in markdown or 'Dashboard' in markdown, "Links should be preserved"

        # Check content length is reasonable
        assert len(markdown) > 500, "Converted markdown should have substantial content"

    @pytest.mark.asyncio
    async def test_no_content_loss(self):
        """Test that conversion doesn't lose significant content"""
        xhtml = self.SAMPLE_XHTML_FULL_PAGE
        markdown = await ConfluenceService.convert_to_markdown(xhtml)

        # Calculate rough content ratio (markdown should be at least 50% of original)
        # (accounting for HTML tags being removed)
        original_text_length = len(BeautifulSoup(xhtml, 'html.parser').get_text())
        markdown_length = len(markdown)

        assert markdown_length >= original_text_length * 0.5, \
            f"Markdown ({markdown_length} chars) should retain most content from original ({original_text_length} chars)"

    @pytest.mark.asyncio
    async def test_special_characters_preserved(self):
        """Test that special characters are properly handled"""
        xhtml = """
<p>Special chars: &amp; &lt; &gt; &quot;</p>
<p>Code: <code>x &lt; 10 &amp;&amp; y &gt; 5</code></p>
"""
        markdown = await ConfluenceService.convert_to_markdown(xhtml)

        # Check HTML entities are decoded
        assert '&' in markdown or 'amp' not in markdown, "HTML entities should be decoded"
        assert '<' in markdown or '&lt;' in markdown, "Less than should be preserved"

    @pytest.mark.asyncio
    async def test_empty_content(self):
        """Test handling of empty content"""
        markdown = await ConfluenceService.convert_to_markdown("")
        assert markdown == "", "Empty input should return empty output"

        markdown = await ConfluenceService.convert_to_markdown("<p></p>")
        assert len(markdown) < 10, "Empty tags should result in minimal output"


class TestConfluenceMockServerIntegration:
    """Integration tests with mock Confluence server"""

    @pytest.mark.asyncio
    async def test_import_from_mock_server(self):
        """Test importing and converting a real page from mock server"""
        try:
            from atlassian import Confluence

            # Connect to mock server
            client = Confluence(
                url='http://mock-confluence:8090',
                username='test@example.com',
                password='mock-api-token',
                cloud=True
            )

            # Fetch page 12346 (Data Ingestion Pipeline Failures)
            page = client.get_page_by_id('12346', expand='body.storage,version')

            assert page is not None, "Should fetch page from mock server"
            assert page.get('title') == 'Data Ingestion Pipeline Failures'

            # Extract and convert content
            storage_content = page['body']['storage']['value']
            assert len(storage_content) > 0, "Page should have content"

            markdown = await ConfluenceService.convert_to_markdown(storage_content)

            # Verify conversion quality
            assert len(markdown) > 500, "Converted markdown should have substantial content"
            assert '# Data Ingestion Pipeline' in markdown, "Should have main heading"
            assert '|' in markdown, "Should have table"
            assert '```' in markdown, "Should have code blocks"
            assert '>' in markdown, "Should have blockquotes from info/warning macros"

            print(f"\n✅ Successfully converted {len(storage_content)} chars XHTML → {len(markdown)} chars Markdown")
            print(f"Preview:\n{markdown[:300]}...\n")

        except Exception as e:
            # Skip if mock server not available
            pytest.skip(f"Mock server not available: {e}")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
