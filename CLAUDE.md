# CLAUDE.md

Project instructions สำหรับ Claude Code เมื่อทำงานกับ repository นี้

## Communication

- สนทนา อธิบาย วิเคราะห์ รายงานผล และสรุปแผนงานกับผู้ใช้เป็นภาษาไทย
- ใช้ภาษาไทยที่อ่านง่ายและตรงประเด็น
- Technical terms สามารถใช้ภาษาอังกฤษได้เมื่อเหมาะสม
- ชื่อไฟล์, file path, class, function, variable, Git branch, Git commit, terminal command, environment variable และ error message ให้คงข้อความเดิม ห้ามแปล
- Documentation ภายใน repository ให้รักษาภาษาเดิมของเอกสาร เว้นแต่ผู้ใช้สั่งให้เปลี่ยนภาษา

## Research Project

โปรเจกต์นี้เป็นงานวิจัย Swarm Robotics แบบ Collective Foraging Simulation

เงื่อนไขการทดลองหลัก:

1. **Condition 1 — Baseline**
   - WM OFF
   - EM OFF
   - Exchange OFF
   - AIH OFF
2. **Condition 2 — Working Memory**
   - WM ON
   - EM OFF
   - Exchange OFF
   - AIH OFF
3. **Condition 3 — Episodic Memory**
   - WM OFF
   - EM ON
   - Exchange OFF
   - AIH OFF
4. **Condition 4**
   - WM ON
   - EM ON
   - Exchange ON แบบไม่บอกทิศทาง
   - AIH OFF
5. **Condition 5**
   - WM ON
   - EM ON
   - Exchange ON แบบบอกทิศทาง
   - AIH OFF
6. **Condition 6**
   - ระบบทั้งหมดเปิดใช้งาน รวม AIH

## Condition 1 Protection

Condition 1 เป็น frozen research control

- ห้ามเปลี่ยน behavior ของ Condition 1 โดยไม่ได้รับคำสั่งจากผู้ใช้โดยตรง
- การพัฒนา Condition 2–6 ต้องไม่ทำให้ Baseline behavior เปลี่ยน
- Feature ใหม่ที่ใช้ shared runner/module ต้องถูก isolate หรือ gate อย่างชัดเจน
- ก่อนแก้ shared module ให้ตรวจผลกระทบต่อ Condition 1 ก่อนเสมอ
- ห้าม overwrite หรือลบผลการทดลอง Condition 1
- ห้าม regenerate frozen Condition 1 research data โดยพลการ
- หากพบการเปลี่ยนแปลงที่อาจ contaminate Condition 1 ให้หยุดและรายงานผู้ใช้ก่อน

## Research Seeds

Canonical research seed set ต้องใช้ชุดเดียวกันสำหรับทุก Condition เพื่อให้เปรียบเทียบกันได้

ห้ามใช้ canonical 20 research seeds สำหรับ development/debugging โดยไม่ได้รับคำสั่งจากผู้ใช้

Development และ regression testing ให้ใช้ development/regression seeds แยกจาก research seeds

## Git Safety

- ตรวจ `git status` ก่อนทำงานสำคัญ
- ห้ามใช้ destructive Git commands เช่น `git reset --hard`, `git clean -fd`, force checkout หรือคำสั่งที่อาจทำให้งานสูญหาย โดยไม่ได้รับอนุญาต
- ห้ามลบ uncommitted work
- ห้าม commit, merge, rebase, tag หรือ push เว้นแต่ผู้ใช้สั่งหรืออนุมัติ
- ก่อน Freeze Condition ใหม่ ต้องตรวจ isolation และ regression กับ Condition 1
- หาก working tree มีไฟล์ที่ไม่เกี่ยวข้องกับงานปัจจุบัน ห้ามแก้หรือลบไฟล์เหล่านั้นเอง

## Working Method

ก่อนเริ่มแก้ระบบสำคัญ:

1. ตรวจสถานะ repository
2. อ่าน documentation ที่เกี่ยวข้อง
3. ตรวจ implementation ปัจจุบัน
4. ระบุผลกระทบที่อาจเกิดกับ Condition อื่น
5. วางแผนการแก้ไข
6. จากนั้นจึงแก้และทดสอบ

เมื่อทำงานเสร็จ ให้รายงานเป็นภาษาไทยว่า:

- แก้อะไร
- แก้ไฟล์ไหน
- ทดสอบอะไร
- PASS/FAIL อย่างไร
- มีความเสี่ยงหรือสิ่งที่ยังไม่ได้ตรวจอะไรบ้าง
- ขั้นตอนถัดไปที่แนะนำคืออะไร
