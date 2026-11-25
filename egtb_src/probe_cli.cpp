// Felicity Egtb 命令行探测封装:  stdin 每行一个 FEN, stdout 输出 "from,dest" 或 "NONE"
// 编译见 build_egtb.bat
#include <iostream>
#include <string>
#include <vector>
#include "Egtb.h"

int main(int argc, const char* argv[]) {
    std::string folder = (argc > 1) ? argv[1] : "./data/egtb";
    egtb::EgtbDb db;
    db.preload(folder, egtb::EgtbMemMode::all, egtb::EgtbLoadMode::loadnow);
    if (db.getSize() == 0) {
        std::cout << "ERROR empty db" << std::endl;
        return 1;
    }

    std::string line;
    while (std::getline(std::cin, line)) {
        if (line.empty()) { std::cout << "NONE" << std::endl; continue; }
        egtb::MoveList moves;
        egtb::EgtbBoard board;
        board.setFen(line);
        int score = db.probe(board, moves);
        (void)score;
        if (!moves.isEmpty()) {
            // 输出残局库给出的最佳首着 (end pos 编码); Python 端做坐标映射与合法性校验
            const egtb::Move& m = moves.list[0];
            std::cout << (int)m.from << "," << (int)m.dest << std::endl;
        } else {
            std::cout << "NONE" << std::endl;
        }
        std::cout.flush();
    }
    return 0;
}
