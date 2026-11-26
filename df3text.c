#include <windows.h>

/* The Korean edition passes CP949 bytes to a transparent TextOutA surface. */
static BYTE glyphs[126 * 256][32];
static BOOL loaded;

static BOOL load_masks(void)
{
    if (loaded) return TRUE;
    HANDLE file = CreateFileA("DF3FONT.BIN", GENERIC_READ, FILE_SHARE_READ, NULL,
                              OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return FALSE;
    DWORD count;
    loaded = ReadFile(file, glyphs, sizeof glyphs, &count, NULL) && count == sizeof glyphs;
    CloseHandle(file);
    return loaded;
}

BOOL WINAPI RenderText(HDC dc, int x, int y, LPCSTR text, int count)
{
    int i = 0;
    while (i < count && (BYTE)text[i] < 0x81) ++i;
    if (i == count || !load_masks()) return TextOutA(dc, x, y, text, count);

    LOGFONTA font;
    if (!GetObjectA(GetCurrentObject(dc, OBJ_FONT), sizeof font, &font))
        return TextOutA(dc, x, y, text, count);
    int size = font.lfHeight < 0 ? -font.lfHeight : font.lfHeight;
    if (size < 1) size = 16;
    HBRUSH brush = CreateSolidBrush(GetTextColor(dc));
    for (i = 0; i < count;) {
        BYTE lead = (BYTE)text[i];
        if (lead < 0x81 || lead > 0xfe || i + 1 == count) {
            SIZE extent;
            TextOutA(dc, x, y, text + i, 1);
            GetTextExtentPoint32A(dc, text + i, 1, &extent);
            x += extent.cx;
            ++i;
            continue;
        }
        const BYTE *mask = glyphs[(lead - 0x81) * 256 + (BYTE)text[i + 1]];
        for (int row = 0; row < size; ++row) {
            int source = (row * 16 / size) * 2;
            WORD bits = (mask[source] << 8) | mask[source + 1];
            for (int col = 0; col < size;) {
                int first = col;
                while (col < size && (bits & (0x8000 >> (col * 16 / size)))) ++col;
                if (col > first) {
                    RECT span = {x + first, y + row, x + col, y + row + 1};
                    FillRect(dc, &span, brush);
                } else ++col;
            }
        }
        x += size;
        i += 2;
    }
    DeleteObject(brush);
    return TRUE;
}
