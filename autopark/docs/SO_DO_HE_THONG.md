# Hiểu AutoPark qua sơ đồ

Hãy tưởng tượng một xe mô hình đang đứng trước chỗ đỗ giữa hai chiếc hộp. Người dùng chọn chỗ đỗ; xe phải tìm cách tiến, lùi và đánh lái để lọt vào đó. Xe cần biết **xung quanh có gì, mình đang ở đâu, đi bằng đường nào và khi nào phải dừng**. Tài liệu này đi theo bốn câu hỏi ấy.

Các hình dưới đây mô tả cách các phần phối hợp với nhau. Chúng không có nghĩa toàn bộ hệ thống đã chạy trên xe thật. AutoPark đã có mô phỏng, phần mềm xử lý cảm biến và một số phép thử bàn; việc tự đỗ trên xe thật vẫn cần kiểm chứng. [Tổng hợp dự án](../../TONG_HOP_DU_AN.md) giải thích mức hoàn thành hiện tại.

## 1. Bức tranh toàn cảnh: một vòng quan sát và hành động

![Từ cảm biến đến bản đồ, tư thế, lập đường, bám đường và phản hồi của xe](images/toan-canh.svg)

*Xe liên tục quan sát kết quả của chuyển động vừa thực hiện để quyết định chuyển động tiếp theo.*

Một vòng làm việc có sáu nhiệm vụ:

| Nhiệm vụ | Câu hỏi cần trả lời | Ví dụ trong bài đỗ giữa hai hộp |
| --- | --- | --- |
| Cảm nhận | Đang nhìn thấy gì? | LiDAR thấy mặt hộp; camera thấy vùng có thể là vật cản |
| Lập bản đồ | Vật đó ở đâu trong sa bàn? | Hộp bên trái chiếm một vùng cụ thể, có mép và kích thước |
| Định vị | Xe ở đâu và đang quay hướng nào? | Đuôi xe cách ô đỗ bao xa, thân xe đang lệch góc bao nhiêu |
| Lập đường | Xe có thể đi vào bằng cách nào? | Tiến ra một đoạn, đánh lái, lùi vào rồi chỉnh thẳng |
| Bám đường | Lúc này cần chạy nhanh và đánh lái bao nhiêu? | Giảm tốc khi gần điểm đổi chiều, sửa độ lệch so với đường |
| Giám sát | Có còn đủ điều kiện tiếp tục? | Dừng nếu xuất hiện hộp mới trên đường hoặc mất tư thế đáng tin |

Tách các nhiệm vụ giúp tìm đúng nguyên nhân khi xe làm sai. Xe đi sát hộp có thể do bản đồ thiếu hộp, định vị lệch, đường quá sát hoặc điều khiển không bám được đường. Thay thuật toán tìm đường chỉ có ích khi lỗi thực sự nằm ở bước tìm đường.

## 2. Một lần đỗ diễn ra như thế nào?

![Luồng từ chọn ô đỗ, kiểm dữ liệu và đường đến thực hiện, hoàn tất hoặc dừng để đánh giá lại](images/luong-do-xe.svg)

*Một lần đỗ có thể kết thúc bằng đỗ thành công hoặc bằng một quyết định dừng có lý do.*

**Trước khi chuyển động**, hệ thống cần một đích đủ rõ: vị trí và hướng cuối cùng của xe. Chỉ chọn một điểm giữa ô chưa đủ; xe có thể đến đúng điểm nhưng nằm chéo, vướng hai bên. Vì vậy bài toán dùng **tư thế đích**, gồm vị trí và góc hướng.

Đường được tìm phải phù hợp với cách xe quay, kích thước toàn thân và khoảng trống quanh xe. Sau đó, xem trước cho biết mô hình xe có bám được đường ấy hay không. Bước này giúp phát hiện một đường đúng về hình học nhưng khó thực hiện khi góc lái thay đổi chậm hoặc khi xe phải đổi chiều.

**Trong lúc chuyển động**, hệ thống tiếp tục nhận dữ liệu mới. Đường cũ chỉ còn giá trị khi các điều kiện dùng để tính nó vẫn còn đúng. Nếu xuất hiện vật cản làm đường mất hiệu lực, xe nhận yêu cầu dừng, cập nhật tình huống và chờ lập lại đường. Hệ thống hiện tại không vừa phanh vừa tự tìm cách lách qua vật mới.

**Đỗ xong** đòi hỏi xe đã đứng yên, sai số vị trí nằm trong dung sai và sai số hướng cũng nằm trong dung sai. Đi hết danh sách điểm của đường chưa đủ để kết luận đỗ thành công.

## 3. Cảm nhận: biến số đo thành chỗ có thể đi

![LiDAR và camera cung cấp bằng chứng, được kiểm chất lượng và quy về cùng bản đồ trước khi tạo vật cản](images/cam-nhan.svg)

*Hai cảm biến bổ sung thông tin cho nhau, nhưng mỗi nguồn vẫn phải giữ dấu thời gian và điều kiện sử dụng.*

**LiDAR** đo khoảng cách theo nhiều hướng. Các điểm đo cho biết hình học quanh xe mà ít phụ thuộc màu sắc của vật. Tuy vậy, LiDAR 2D chủ yếu quan sát một mặt phẳng quét: một vật thấp hơn mặt phẳng đó có thể không xuất hiện trong số đo.

**Camera** cho thông tin về bề mặt và hình dạng trong ảnh. Mô hình phân vùng ảnh đánh dấu những vùng có khả năng là vật cản; đây là một nguồn bổ sung cho những gì LiDAR có thể bỏ sót. Khó khăn là một điểm trên ảnh chưa nói ngay được vật nằm cách xe bao nhiêu. Cần biết đặc tính ống kính, vị trí gắn camera và vùng ảnh có thể dùng; sau đó mới quy thông tin ảnh về mặt đất trong sa bàn.

Bản đồ chia không gian thành các ô có ba trạng thái: **đã thấy trống, có vật cản, chưa biết**. “Chưa thấy vật” và “đã thấy trống” là hai loại bằng chứng khác nhau. Bóng che, vùng ngoài ảnh và cảm biến bị mất dữ liệu đều có thể tạo ra vùng chưa biết.

Để tránh một điểm nhiễu làm xe dừng liên tục, các lớp vật cản dùng bằng chứng lặp lại qua nhiều lần quan sát. Sự đánh đổi rất cụ thể: lọc nhiều hơn giúp bớt báo nhầm nhưng làm phát hiện vật mới chậm hơn. Cần đo cả độ trễ lẫn số lần bỏ sót, nhất là với vật nhỏ.

Trong luồng hiện có, camera **bổ sung vật cản** cho bài toán lập đường; nhận định “trống” của camera không xóa vật cản do LiDAR hoặc người dùng cung cấp. Camera thiếu hiệu chuẩn hoặc dữ liệu không hợp lệ chưa được phép đóng vai trò nguồn vật cản đã đo. Khả năng camera nhìn ra vật thấp cũng phải được xác nhận trên sa bàn thật, không thể suy ra chỉ từ một ảnh minh họa đẹp.

## 4. Định vị: đặt xe vào đúng bản đồ

![Khớp quét với bản đồ cố định, dự đoán chuyển động giữa các lần quét và kiểm chéo trước khi công bố tư thế](images/dinh-vi.svg)

*Một tọa độ chỉ có ích khi hệ thống còn biết vì sao có thể tin tọa độ ấy.*

Biết “có hộp cách LiDAR nửa mét” chưa đủ. Bộ lập đường cần biết hộp và xe nằm ở đâu **trong cùng một hệ tọa độ**. Nếu xe tưởng mình ở bên trái vị trí thật vài centimét, một đường nhìn có vẻ đủ rộng có thể đưa thân xe chạm hộp.

AutoPark hiện kết hợp hai cách ước lượng:

| Cách làm | Ý tưởng dễ hình dung | Lý do sử dụng và giới hạn |
| --- | --- | --- |
| Khớp vòng quét với bản đồ cố định | Dịch và xoay đám điểm đo để chúng trùng với các bức tường, mép hộp đã biết | Tạo mốc vị trí trong sa bàn; dễ mơ hồ khi hai nơi có hình dạng giống nhau |
| Khớp các vòng quét gần nhau | Nhìn sự thay đổi của cảnh để đoán xe vừa dịch và quay bao nhiêu | Giúp thu hẹp vùng tìm và kiểm chéo; sai số có thể tích lũy theo quãng đi |

Cách thứ nhất tìm trên một lưới vị trí và góc, giữ những vị trí phù hợp rồi tinh chỉnh. Cách thứ hai cung cấp dự đoán chuyển động để lần tìm tiếp theo không phải dò lại toàn sa bàn. Hai kết quả bất đồng là dấu hiệu cần đánh giá lại. Chúng cùng dùng LiDAR nên **không phải hai nguồn đo độc lập**: một cảnh ít đặc trưng vẫn có thể gây khó cho cả hai.

Ví dụ, đứng giữa một hành lang dài và đều, xe có thể nhận ra khoảng cách tới hai bên rất tốt nhưng khó biết mình đã đi dọc hành lang bao xa. Báo “không đủ chắc” hữu ích hơn việc luôn trả về một tọa độ có vẻ chính xác.

Luồng này dùng **bản đồ cố định**, chưa phải một hệ SLAM hoàn chỉnh vừa xây bản đồ khi chạy vừa xử lý quay lại nơi cũ. Cách chọn này giúp tách riêng việc kiểm bản đồ với việc kiểm định vị trong sa bàn giới hạn. Đổi lại, bản đồ phải đủ đúng và phải phân biệt vật cản mới với các mốc ổn định dùng để định vị.

## 5. Lập đường: tìm chuyển động mà xe thực hiện được

![Tư thế đầu, đích và vật cản đi qua các chiến lược tìm kiếm và kiểm toàn thân xe để nhận một đường có thể thực hiện](images/lap-duong.svg)

*Cần kiểm cả đường đi lẫn khả năng bám đường trước khi chấp nhận kết quả.*

Xe kiểu ô tô không thể trượt ngang vào ô đỗ. Xe phải tiến hoặc lùi, đồng thời quay với bán kính bị giới hạn bởi chiều dài cơ sở và góc lái. Vì vậy, đường nối hai điểm trong mặt phẳng chưa giải quyết được bài toán đỗ.

AutoPark tìm trong không gian có **vị trí, hướng và chiều chuyển động**. Các họ thuật toán bổ sung cho nhau:

| Thành phần | Giải quyết khó khăn nào? | Vì sao hữu ích ở đây? |
| --- | --- | --- |
| Các đoạn chuyển động mẫu và tìm kiếm lattice | Có rất nhiều cách tiến, lùi, đánh lái | Ghép những đoạn xe có thể thực hiện để thử phương án nhanh trước |
| Reeds–Shepp | Nối hai tư thế của xe có khả năng tiến và lùi | Cung cấp các tổ hợp cung tròn, đoạn thẳng hợp với giới hạn quay; vẫn phải kiểm vật cản |
| RRT-Connect | Khoảng trống có hình dạng khó, tìm kiếm đều quá tốn công | Mở rộng hai cây từ đầu và đích để tìm cách nối; kết quả và thời gian có thể thay đổi giữa các lần tìm |
| Hybrid A* | Cần xét chuyển động liên tục nhưng vẫn kiểm soát số trạng thái tìm | Mô phỏng các bước xe thực sự đi được, đồng thời gom trạng thái gần nhau vào ô tìm kiếm |

Luồng mặc định thử lattice nhanh, lattice kỹ hơn, RRT-Connect có kết nối Reeds–Shepp, rồi Hybrid A* với độ phân giải mịn. Thử nhiều cách làm tăng cơ hội tìm được đường trong giới hạn thời gian; không đồng nghĩa đường trả về luôn là đường ngắn nhất có thể.

Đường còn phải qua kiểm tra **toàn thân xe**: đầu xe có thể quét ra ngoài khi đuôi xe đang lùi vào, và góc thân xe có thể chạm hộp dù tâm xe không chạm. Khoảng hở dự phòng cần tính đến sai số bản đồ, định vị và bám đường. Nới khoảng hở quá nhiều sẽ làm nhiều ô đỗ trở nên không thể vào; nới quá ít thì kết quả phụ thuộc quá mạnh vào số đo lý tưởng.

Để hiểu sâu từng lựa chọn và những phương án thay thế, đọc [thuật toán tìm và bám đường](THUAT_TOAN_DUONG_DI.md).

## 6. Bám đường: sửa sai sau mỗi chuyển động

![Đường tham chiếu và tư thế đo tạo sai số, bộ điều khiển chọn tốc độ cùng góc lái, xe chuyển động và phản hồi trở lại](images/bam-duong.svg)

*Lệnh dự kiến tạo chuyển động; số đo mới cho biết chuyển động thực tế đã lệch bao nhiêu.*

Đường đã chọn là một dự định. Khi thực hiện, xe có thể đánh lái chậm, lệch tốc độ hoặc nhận tư thế trễ. Nếu chỉ phát lại một chuỗi lệnh định sẵn, sai số sẽ tích lũy mà không được sửa.

Bộ bám hiện tại dùng **góc lái dự kiến từ đường**, cộng với hai phần sửa sai:

- **Sai số ngang:** xe đang lệch sang bên nào so với đường?
- **Sai số hướng:** đầu xe đang quay lệch bao nhiêu so với hướng cần có?

Góc lái dự kiến giúp xe chủ động đi theo cung cong; phản hồi giúp kéo xe về khi thực tế không khớp dự định. Khi lùi, quan hệ giữa đánh lái và thay đổi hướng khác lúc tiến, nên quy tắc sửa sai phải xét chiều chuyển động. Đây là bộ bám kết hợp dự kiến và phản hồi; không phải Pure Pursuit thuần.

Tốc độ giảm khi gần cuối đoạn. Ở chỗ đổi từ tiến sang lùi hoặc ngược lại, xe phải dừng hẳn rồi mới chuyển đoạn. Tăng độ mạnh của phần sửa sai có thể giúp kéo về đường nhanh hơn nhưng cũng dễ gây dao động khi dữ liệu trễ; chọn hệ số cần dựa trên chuyển động và số đo thực tế.

Thiết kế chia việc giữa máy tính và bo trên xe. Máy tính xử lý bản đồ, định vị, lập đường và bám đường. Bo nhận yêu cầu tốc độ, góc lái và áp giới hạn tại chỗ; các cơ cấu như động cơ, bộ điều tốc và servo thực hiện chuyển động. Mã điều khiển bo và bo ảo đã có, nhưng phản hồi cảm biến cùng tác động điện, cơ trên xe thật vẫn là phần cần hoàn thiện và đo.

## 7. Dừng: một quyết định cần được xác nhận

![Các nguyên nhân dừng dẫn đến yêu cầu dừng, xác nhận bằng dữ liệu mới rồi đánh giá lại; không xác nhận được thì ghi lỗi](images/an-toan.svg)

*“Đã gửi yêu cầu dừng” và “đã xác nhận xe đứng yên” là hai mốc khác nhau.*

Giả sử một chiếc hộp mới xuất hiện đúng nơi xe sắp đi qua. Luồng xử lý hiện có ưu tiên dừng và làm mất hiệu lực đường cũ. Xe chỉ có thể tiếp tục sau khi tình huống được đánh giá lại và có đường phù hợp. Với dữ liệu cảm biến, hệ thống xét vật mới có chạm vùng toàn thân xe sẽ đi qua hay không; một vật ở xa đường không nhất thiết khiến xe dừng.

**Dấu thời gian là một phần của số đo.** Tọa độ đúng ở nửa giây trước có thể đã sai đối với hiện tại. Nếu nguồn định vị ngừng cập nhật, việc vẽ lại tọa độ cũ không biến nó thành số đo mới. Mất dữ liệu, dữ liệu quá cũ hoặc tư thế không đủ tin cậy đều có thể làm phiên dừng. Dữ liệu quay lại không tự động cho phép xe chạy tiếp.

Đối với luồng điều khiển qua bo, xác nhận đứng yên cần phản hồi mới về tốc độ. Nếu hết thời hạn mà chưa có xác nhận, kết quả là **lỗi chưa xác nhận dừng**. Chế độ quan sát có ý nghĩa khác: phần mềm chỉ tính và ghi đề xuất, người lái điều khiển xe; kết thúc quan sát không có nghĩa phần mềm đã phanh xe.

Thiết kế có ba lớp bảo vệ, với phạm vi khác nhau:

| Lớp | Tình huống cần xử lý | Mức đã được kiểm chứng |
| --- | --- | --- |
| Máy tính | Vật cản mới trên đường, dữ liệu cũ, mất định vị | Logic phần mềm, mô phỏng và một số luồng cảm biến bàn thử |
| Bo điều khiển | Lệnh quá hạn hoặc mất liên lạc với máy tính | Logic lõi và một phần thực thi trên bo ảo |
| Dừng khẩn phần cứng | Phần mềm hoặc đường truyền không còn đáp ứng | Đang ở mức thiết kế, chưa có phép đo xác nhận trên xe |

Ba lớp tồn tại vì một chương trình không thể tự bảo đảm phản ứng của chính nó khi bị treo. Tuy nhiên, một lệnh dừng đúng về logic vẫn chưa cho biết xe trôi thêm bao xa. Thời gian phản ứng, quãng dừng, phản ứng của bộ điều tốc và tác dụng của nút dừng khẩn cần được đo trên phần cứng thật.

## 8. Kiểm chứng: mỗi phép thử trả lời một câu hỏi

![Từ câu hỏi và giả thuyết đến mô phỏng, bàn thử, xe thật rồi kết luận theo phạm vi bằng chứng](images/bang-chung.svg)

*Kết quả ở mỗi mức giúp quyết định bước tiếp theo, nhưng không thay thế kết quả ở mức khác.*

Một đường đỗ đẹp trên màn hình là bằng chứng rằng một số ý tưởng phối hợp được dưới các giả định đã chọn. Để biết xe thật có làm được hay không, cần lần lượt kiểm những giả định ấy.

| Mức thử | Câu hỏi trả lời được | Điều còn phải đo ở bước sau |
| --- | --- | --- |
| Mô phỏng | Với kích thước, cảm biến và chuyển động giả định, xe có tìm và bám được đường? | Tham số thật, nhiễu thật, ma sát và độ trễ cơ cấu |
| Bo ảo | Phần mềm trên bo có trao đổi lệnh và phản ứng logic theo thiết kế? | Xung điện, chân tín hiệu, cảm biến và dừng vật lý |
| Bàn thử cảm biến | Thiết bị có đo được cảnh thật, dữ liệu có ổn định? | Ảnh hưởng của gá lắp, rung, nguồn điện và chuyển động trên xe |
| Xe thật | Toàn bộ chuỗi có đỗ và dừng đúng trong tình huống đã thử? | Những tình huống, bề mặt và điều kiện chưa được thử |

Một lượt đánh giá nên ghi sai số vị trí cuối, sai số hướng, khoảng hở nhỏ nhất, số lần đổi chiều, thời gian và lý do kết thúc. Với cảm nhận, cần thêm số lần bỏ sót và báo nhầm; với dừng, cần thời gian từ sự kiện đến phản ứng và quãng đường xe đi thêm.

Đo sai số vị trí cần một **tham chiếu độc lập**: chẳng hạn một hệ đo từ trên cao được hiệu chuẩn phù hợp. Nếu dùng chính vị trí mà bộ định vị tự báo để chấm bộ định vị ấy, sai số chung có thể bị che mất. Công cụ tham chiếu bằng dấu ArUco đã được chuẩn bị trong dự án, nhưng bằng chứng ảnh tổng hợp chưa thay cho một hệ đo thật đã kiểm chuẩn.

Giữ lại những lần thất bại rất có ích. Chúng cho biết hệ thống đang yếu ở bước cảm nhận, định vị, tìm đường hay điều khiển, từ đó giúp chọn đúng vấn đề để cải thiện.

## 9. Đọc tiếp và tham gia vào bài toán

Người mới có thể bắt đầu từ một tình huống nhỏ: vật thấp bị LiDAR bỏ sót, hành lang khiến vị trí mơ hồ, ô đỗ hẹp cần nhiều lần đổi chiều, hoặc dữ liệu trễ khiến xe bám đường kém. Mỗi tình huống đều cần nêu được điều đang thiếu, lý do chọn cách giải và phép đo dùng để đánh giá.

- [Cảm nhận và định vị](CAM_NHAN_VA_DINH_VI.md): tìm hiểu vì sao kết hợp LiDAR, camera và các cách ước lượng tư thế.
- [Thuật toán tìm và bám đường](THUAT_TOAN_DUONG_DI.md): hiểu các lựa chọn cho chuyển động tiến, lùi và sửa sai khi đỗ.
- [Cách tham gia giải quyết bài toán AutoPark](../../CONTRIBUTING.md): ví dụ đi từ một quan sát đến giả thuyết và kết luận có bằng chứng.
- [Thuật ngữ](THUAT_NGU.md): giải thích từ chuyên môn bằng tình huống của dự án.
- [Tổng hợp dự án](../../TONG_HOP_DU_AN.md): biết phần nào đã có và câu hỏi nào còn mở.
- [Mục lục tài liệu](README.md): tra các chuyên đề và hồ sơ phép đo khi cần đi sâu.

Các sơ đồ ở đây lược bỏ chi tiết để giữ mạch ý tưởng. Ngưỡng kỹ thuật, phép đo và giới hạn cụ thể cần đọc trong chuyên đề tương ứng; đặc biệt, không coi kết quả mô phỏng là kết quả tự đỗ trên xe thật.

Các hồ sơ cũ dẫn theo số mục chi tiết có thể tra [bản sơ đồ trước lần viết lại này](https://github.com/thbn12082/autopark/blob/21cdb2d/autopark/docs/SO_DO_HE_THONG.md).
