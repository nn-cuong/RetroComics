# RetroComics App

Một ứng dụng đọc truyện tranh, Manga, Comics và tài liệu PDF mã nguồn mở, được thiết kế và tối ưu hóa đặc biệt cho thiết bị **TrimUI Brick Pro** (màn hình IPS 1024×768, vi xử lý Allwinner A133p, TrimUI OS). Ứng dụng là phiên bản chuyên biệt của hệ sinh thái đọc sách song hành cùng RetroBooks.

---

## 🌟 Tính năng nổi bật

- **Hỗ trợ định dạng toàn diện:** Đọc trực tiếp các định dạng truyện tranh và tệp nén thông dụng: **PDF, CBZ, CBR, CB7, ZIP, RAR, 7Z, CBT, TAR**, cùng các thư mục ảnh rời (`.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`).
- **Chế độ hiển thị thư viện kép (Dual-Mode Library View):**
  - Chuyển đổi linh hoạt giữa **List View** (Danh sách truyền thống với icon truyện đồng bộ) và **Grid View** (Lưới bìa 4×2, 8 cuốn/trang với ảnh bìa thực tế) chỉ bằng một nút bấm (**Nút B vật lý**).
  - Tự động trích xuất ảnh bìa thực tế từ trang đầu của tệp truyện tranh và lưu bộ nhớ đệm RAM thông minh.
  - Thẻ bìa Hardcover sang trọng với tên sách dập chìm thanh lịch khi tệp chưa có ảnh bìa hoặc đang trong quá trình quét.
  - Tự động lưu chế độ xem yêu thích vào bộ nhớ cấu hình.
- **6 Bộ chủ đề màu sắc chuyên sâu:**
  1. **Vintage Dark** *(Mặc định)* — Nâu cổ điển ấm áp.
  2. **Night Mode** — Xám than hiện đại, độ tương phản cao.
  3. **Paper** — Giấy ngà tự nhiên, thân thiện với thị giác.
  4. **Warm Night** — Ánh sáng hổ phách ấm giúp bảo vệ mắt ban đêm.
  5. **AMOLED Black** — Nền đen sâu tối giản, tiết kiệm pin.
  6. **Forest** — Xanh rêu thư viện thanh bình và tĩnh lặng.
- **Trình đọc chuyên sâu (Reader Experience):**
  - **Phóng to & Di chuyển (Zoom & Pan):** Phóng to linh hoạt từ Fit-to-screen đến 8x bằng **Nút Y** (phóng to) và **Nút B** (thu nhỏ). Di chuyển quanh khung hình mượt mà bằng D-pad hoặc Analog Joystick.
  - **Xoay màn hình 4 hướng (0°, 90°, 180°, 270°):** Nhấn **Nút X** để xoay máy đọc ngang/dọc tùy ý; hệ thống tự động đồng bộ chiều điều khiển D-pad và Joystick theo đúng hướng mắt nhìn.

---

## 🎮 Bảng nút điều khiển (Controller Mapping)

### 1. Trong Thư viện (Library)
| Nút vật lý trên TrimUI | Thao tác tương ứng |
| :--- | :--- |
| **D-pad / Analog Lên / Xuống** | Di chuyển giữa các cuốn truyện (trong List) hoặc hàng trên/dưới (trong Grid) |
| **D-pad / Analog Trái / Phải** | Nhảy trang (trong List) hoặc di chuyển cột trái/phải (trong Grid) |
| **Nút A** | Mở đọc cuốn truyện đang chọn / Vào thư mục |
| **Nút B** | **Chuyển đổi giao diện Thư viện: [LIST VIEW] $\leftrightarrow$ [GRID VIEW]** |
| **Nút Y** | Chuyển đổi qua lại giữa **6 Chủ đề giao diện (Theme)** |
| **Nút vai L1 / R1** | Nhảy nhanh 8 cuốn truyện (Page Up / Page Down) |
| **Nút START** | Mở hộp thoại xác nhận thoát ứng dụng (A: Thoát, B: Hủy) |

---

### 2. Khi đang Đọc truyện (Reader)
| Nút vật lý trên TrimUI | Thao tác tương ứng |
| :--- | :--- |
| **D-pad / Analog Joystick** | Di chuyển góc nhìn quanh trang ảnh (Pan khi đang phóng to) |
| **D-pad Trái / Phải** | Lật sang trang Trước / Sau |
| **Nút vai L1 / R1** | Lật sang trang Trước / Sau |
| **Cò vai L2 / R2** | Mở cửa sổ Nhảy trang nhanh (Page Jump Dialog) |
| **Nút A** | Bật / Tắt thanh thông tin hiển thị (HUD) |
| **Nút Y** | Phóng to ảnh (Zoom In) |
| **Nút B** | Thu nhỏ ảnh (Zoom Out) |
| **Nút X** | Xoay hướng màn hình 90° (0° $\rightarrow$ 90° $\rightarrow$ 180° $\rightarrow$ 270°) |
| **Nút SELECT** | Đóng truyện, lưu tiến trình và trở về Thư viện sách |
| **Nút START** | Mở hộp thoại xác nhận thoát ứng dụng |

---

## ⚙️ Hướng dẫn cài đặt

Để cài đặt ứng dụng lên máy TrimUI của bạn, chỉ cần làm theo các bước đơn giản sau:

1. Bấm vào nút `<> Code` màu xanh lá ở trên Github, sau đó chọn **Download ZIP** để tải mã nguồn về máy tính.
2. Giải nén file ZIP vừa tải ra, đảm bảo thư mục giải nén được đặt tên là `RetroComics`.
3. **Copy toàn bộ thư mục `RetroComics` đó và dán vào thư mục `Apps` nằm trên thẻ nhớ (SD Card) của máy.**
4. Chép truyện tranh hoặc tài liệu của bạn (`.pdf`, `.cbz`, `.cbr`, `.zip`, `.rar`,...) vào thư mục `Books` nằm ở thư mục gốc của thẻ nhớ SD (`/mnt/SDCARD/Books`).
5. Lắp thẻ nhớ vào máy TrimUI, ứng dụng sẽ tự động xuất hiện trong giao diện menu Apps.

---

## 📜 Tuyên bố Mã nguồn mở (Open Source) & Bản quyền

Dự án này là mã nguồn mở và được phát hành dưới giấy phép **MIT License**. Bạn hoàn toàn có thể tự do sử dụng, học hỏi, sao chép hoặc phát triển thêm.

- **Tác giả gốc (Original Creator):** Nguyễn Ngọc Cường
- **Email liên hệ:** nn.cuong.404@gmail.com

Khi sử dụng lại hoặc tùy biến mã nguồn này, vui lòng giữ nguyên thông tin tác giả và bản quyền gốc theo quy định của giấy phép MIT đính kèm trong repository này.
