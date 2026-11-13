/**
 * Markdown Lite - lightweight markdown to HTML for mini program rich-text
 * 
 * Supports: bold, italic, inline code, code blocks, lists, headers, links, line breaks
 */

function markdownToHtml(text) {
  if (!text) return '';

  var html = text;

  // Extract and protect code blocks before HTML escaping
  var codeBlocks = [];
  html = html.replace(/```([\w]*)\n?([\s\S]*?)```/g, function(match, lang, code) {
    var escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    var idx = codeBlocks.length;
    codeBlocks.push('<div style="background:#f7f8fa;padding:20rpx 24rpx;border-radius:8rpx;margin:20rpx 0;font-size:26rpx;font-family:\'SF Mono\',Monaco,monospace;white-space:pre-wrap;overflow-x:auto;color:#24292f;border:2rpx solid #e8e8ea;line-height:1.5;">' + escaped + '</div>');
    return '\x00CODE' + idx + '\x00';
  });

  // Escape remaining HTML special chars
  html = html.replace(/&/g, '&amp;');
  html = html.replace(/</g, '&lt;');
  html = html.replace(/>/g, '&gt;');

  // Inline code (`code`)
  html = html.replace(/`([^`]+)`/g, '<code style="background:#f0f0f0;padding:4rpx 8rpx;border-radius:4rpx;font-size:28rpx;font-family:monospace;color:#e83e8c;">$1</code>');

  // Bold (**text** or __text__)
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong style="font-weight:600;color:#1a1a1a;">$1</strong>');
  html = html.replace(/__(.+?)__/g, '<strong style="font-weight:600;color:#1a1a1a;">$1</strong>');

  // Italic (*text*)
  html = html.replace(/\*([^*\n]+)\*/g, '<em style="font-style:italic;">$1</em>');

  // Horizontal rule
  html = html.replace(/^---+$/gm, '<div style="border-top:2rpx solid #e8e8ea;margin:20rpx 0;"></div>');

  // Headers (# ## ###)
  html = html.replace(/^### (.+)$/gm, '<div style="font-size:32rpx;font-weight:700;margin:24rpx 0 12rpx;color:#1a1a1a;">$1</div>');
  html = html.replace(/^## (.+)$/gm, '<div style="font-size:34rpx;font-weight:700;margin:28rpx 0 14rpx;color:#1a1a1a;">$1</div>');
  html = html.replace(/^# (.+)$/gm, '<div style="font-size:38rpx;font-weight:700;margin:28rpx 0 14rpx;color:#1a1a1a;">$1</div>');

  // Unordered list (- item or * item)
  html = html.replace(/^[\-\*] (.+)$/gm, '<div style="padding-left:32rpx;margin:4rpx 0;line-height:1.7;position:relative;"><span style="position:absolute;left:0;top:0;color:#666;">•</span><span>$1</span></div>');

  // Ordered list (1. item)
  (function() {
    var counter = 0;
    html = html.replace(/^\d+\. (.+)$/gm, function(match, p1) {
      counter++;
      return '<div style="padding-left:32rpx;margin:4rpx 0;line-height:1.7;position:relative;"><span style="position:absolute;left:0;top:0;color:#666;min-width:28rpx;">' + counter + '.</span><span>' + p1 + '</span></div>';
    });
  })();

  // Links [text](url)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<span style="color:#5c5cff;text-decoration:underline;">$1</span>');

  // Block quotes (> text)
  html = html.replace(/^&gt; (.+)$/gm, '<div style="border-left:6rpx solid #e8e8ea;padding:12rpx 20rpx;color:#666;margin:16rpx 0;background:#f7f8fa;border-radius:0 8rpx 8rpx 0;">$1</div>');

  // Tables (| header | header |)
  html = html.replace(/(\|.+\|[\r\n]+\|[\s\-:]+\|[\r\n]+(?:\|.+\|[\r\n]*)+)/gm, function(match) {
    var lines = match.trim().split(/[\r\n]+/);
    if (lines.length < 3) return match;
    
    var tableHtml = '<div style="overflow-x:auto;margin:16rpx 0;"><table style="border-collapse:collapse;width:100%;font-size:28rpx;">';
    
    // Header row
    var headers = lines[0].split('|').filter(function(cell) { return cell.trim(); });
    tableHtml += '<thead><tr style="background:#f7f8fa;">';
    headers.forEach(function(cell) {
      tableHtml += '<th style="border:2rpx solid #e8e8ea;padding:12rpx 16rpx;text-align:left;font-weight:600;color:#1a1a1a;">' + cell.trim() + '</th>';
    });
    tableHtml += '</tr></thead>';
    
    // Body rows
    tableHtml += '<tbody>';
    for (var i = 2; i < lines.length; i++) {
      var cells = lines[i].split('|').filter(function(cell) { return cell.trim(); });
      if (cells.length === 0) continue;
      tableHtml += '<tr>';
      cells.forEach(function(cell) {
        tableHtml += '<td style="border:2rpx solid #e8e8ea;padding:12rpx 16rpx;color:#333;">' + cell.trim() + '</td>';
      });
      tableHtml += '</tr>';
    }
    tableHtml += '</tbody></table></div>';
    
    return tableHtml;
  });

  // Double newline → paragraph break
  html = html.replace(/\n{2,}/g, '<br/><br/>');

  // Single newline → line break
  html = html.replace(/\n/g, '<br/>');

  // Restore code blocks
  html = html.replace(/\x00CODE(\d+)\x00/g, function(match, idx) {
    return codeBlocks[parseInt(idx)];
  });

  return '<div style="font-size:30rpx;line-height:1.6;color:#1a1a1a;word-break:break-word;">' + html + '</div>';
}

module.exports = { markdownToHtml };
